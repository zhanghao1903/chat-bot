from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import PIL
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from group_llm_agent.expression import canonical_json_bytes, file_sha256

_ASSET_VERSION = "lezhi-expression-v0.3"
_PERSONA_ID = "lezhi"
_PERSONA_VERSION = "lezhi-v2.0"
_PERSONA_DIGEST = "0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603"
_CANVAS_SIZE = 512
_CONTENT_SIZE = 472


@dataclass(frozen=True)
class LockedSource:
    source_id: str
    filename: str
    sha256: str
    dimensions: tuple[int, int]
    mode: str
    sheet: str | None


@dataclass(frozen=True)
class CellSpec:
    sheet: str
    row: int
    column: int
    visible_text: str
    slug: str
    action: str
    emotion: str
    interaction_intent: str
    minimum_relationship: str
    emoji: str

    @property
    def coordinate(self) -> str:
        return f"{self.sheet}{(self.row - 1) * 4 + self.column:02d}"

    @property
    def semantic_id(self) -> str:
        return f"lezhi.{self.slug}.{self.coordinate.lower()}"


LOCKED_SOURCES = (
    LockedSource(
        "visual-source-001",
        "character.png",
        "78038c88dd23716dd532d1d8fb6e384917e2d9029142ce8d10b43fe1d816be0d",
        (1448, 1086),
        "RGBA",
        None,
    ),
    LockedSource(
        "sticker-sheet-a",
        "dd70bd79-83db-4cc2-95f6-8066dcc2e5a1.png",
        "c384adec02358e02981ce338ab3ef45b5ac36bb7e54f9451f9f60c0218626ff8",
        (1254, 1254),
        "RGB",
        "A",
    ),
    LockedSource(
        "sticker-sheet-b",
        "715b4367-000d-485d-ba57-99b035c16ddf.png",
        "2ab2c46964735fdde6b93715969519a5479536a7b2ced378e655f156e6bb5c3e",
        (1254, 1254),
        "RGB",
        "B",
    ),
    LockedSource(
        "sticker-sheet-c",
        "4068900b-a83a-456f-9c04-4aacabecb730.png",
        "895a2e149aa621fcecd51f83272c185f5986604e13be94bb15be68b4d18e9f2c",
        (1254, 1254),
        "RGB",
        "C",
    ),
)


def _cell(
    sheet: str,
    index: int,
    text: str,
    slug: str,
    action: str,
    emotion: str,
    intent: str,
    relationship: str,
    emoji: str,
) -> CellSpec:
    return CellSpec(
        sheet,
        (index - 1) // 4 + 1,
        (index - 1) % 4 + 1,
        text,
        slug,
        action,
        emotion,
        intent,
        relationship,
        emoji,
    )


CELL_SPECS = (
    _cell("A", 1, "嗨～", "hello_wave", "挥手问候", "明快", "greeting", "public", "👋"),
    _cell("A", 2, "收到", "acknowledged", "比出确认手势", "可靠", "acknowledge", "public", "👌"),
    _cell("A", 3, "我在听", "listening", "侧耳倾听", "专注", "listen", "public", "👂"),
    _cell("A", 4, "有点在意", "quietly_caring", "轻声关心", "在意", "care", "familiar", "💙"),
    _cell("A", 5, "让我想想", "thinking", "托腮思考", "思索", "think", "public", "🤔"),
    _cell("A", 6, "这个不错", "approving", "竖起拇指", "认可", "approve", "public", "👍"),
    _cell("A", 7, "笑死我了", "laughing", "捂嘴大笑", "欢乐", "amuse", "familiar", "😂"),
    _cell("A", 8, "冲呀", "cheering", "挥拳加油", "振奋", "encourage", "public", "💪"),
    _cell("A", 9, "抱歉呀", "apologetic", "合掌道歉", "歉意", "apologize", "public", "🙏"),
    _cell("A", 10, "嗯？", "curious_huh", "歪头疑问", "好奇", "clarify", "public", "❓"),
    _cell("A", 11, "先别急", "calming", "抬手安抚", "沉着", "calm", "public", "🫶"),
    _cell("A", 12, "查一下", "checking", "拿出平板查询", "认真", "investigate", "public", "🔎"),
    _cell(
        "A", 13, "好耶", "celebrate_open_arms", "张开双臂庆祝", "雀跃", "celebrate", "public", "🎉"
    ),
    _cell("A", 14, "辛苦啦", "appreciation", "合掌致谢", "温暖", "appreciate", "public", "🌷"),
    _cell("A", 15, "晚安", "good_night", "抱着海豚入睡", "安宁", "sleep", "familiar", "🌙"),
    _cell("A", 16, "贴贴", "cuddle_dolphin", "拥抱海豚贴近", "亲昵", "affection", "close", "💞"),
    _cell("B", 1, "哼哼", "smug_hmph", "抱臂轻哼", "得意", "tease", "familiar", "😏"),
    _cell("B", 2, "你猜", "playful_guess", "眨眼卖关子", "俏皮", "tease", "familiar", "😉"),
    _cell("B", 3, "略略略", "tongue_tease", "吐舌做鬼脸", "淘气", "tease", "close", "😝"),
    _cell("B", 4, "装一下", "feigned_cool", "闭眼摆姿态", "自得", "style", "familiar", "✨"),
    _cell(
        "B", 5, "拿捏了", "confident_got_it", "自信指向前方", "笃定", "confidence", "public", "😎"
    ),
    _cell(
        "B", 6, "本小姐登场", "grand_entrance", "张开双臂登场", "张扬", "greeting", "familiar", "🌟"
    ),
    _cell("B", 7, "优雅", "elegant_tea", "端杯品茶", "从容", "style", "public", "☕"),
    _cell("B", 8, "看戏", "watching_drama", "躲在帘后围观", "好奇", "observe", "familiar", "👀"),
    _cell("B", 9, "嘻嘻", "bashful_giggle", "捂嘴偷笑", "甜美", "amuse", "familiar", "🤭"),
    _cell("B", 10, "别管我啦", "carefree_play", "抱着海豚玩闹", "自在", "tease", "familiar", "🐬"),
    _cell(
        "B", 11, "懂了吧", "knowing_point", "眨眼比出手势", "机灵", "acknowledge", "familiar", "💡"
    ),
    _cell("B", 12, "高深", "mock_profound", "托腮故作深沉", "装深沉", "tease", "familiar", "🧐"),
    _cell("B", 13, "不许笑", "mock_annoyed", "抱臂脸红", "羞恼", "boundary", "familiar", "😤"),
    _cell("B", 14, "哎呦喂", "flustered", "慌张伸手", "惊慌", "react", "public", "😵"),
    _cell("B", 15, "骗你的", "just_kidding", "眨眼做噤声手势", "顽皮", "tease", "familiar", "🤫"),
    _cell(
        "B", 16, "欠欠的", "mischievous_cuddle", "坏笑抱海豚", "欠揍式俏皮", "tease", "close", "😼"
    ),
    _cell("C", 1, "啊？！", "startled_question", "捧脸惊叫", "惊讶", "react", "public", "😲"),
    _cell("C", 2, "等等", "wait_stop", "伸手叫停", "急切", "boundary", "public", "✋"),
    _cell("C", 3, "震惊", "shocked_blank", "瞪大眼睛僵住", "震撼", "react", "public", "😳"),
    _cell("C", 4, "我裂开了", "devastated_cry", "大哭崩溃", "崩溃", "distress", "familiar", "😭"),
    _cell("C", 5, "别吓我", "frightened", "后退摆手", "受惊", "react", "public", "😨"),
    _cell(
        "C", 6, "离谱", "absurd_point", "指向荒唐之事", "难以置信", "skepticism", "familiar", "🙃"
    ),
    _cell("C", 7, "气鼓鼓", "pouting", "抱臂生闷气", "不满", "boundary", "familiar", "😠"),
    _cell("C", 8, "呜呜", "crying", "捂嘴落泪", "委屈", "distress", "familiar", "🥺"),
    _cell("C", 9, "真的假的", "skeptical", "托腮质疑", "怀疑", "skepticism", "public", "🤨"),
    _cell("C", 10, "脑袋宕机", "overloaded", "眼冒圈圈停机", "混乱", "confuse", "public", "🌀"),
    _cell("C", 11, "救命", "calling_help", "伸手求救", "慌乱", "rescue", "familiar", "🛟"),
    _cell("C", 12, "好耶", "celebrate_fist", "握拳欢呼", "兴奋", "celebrate", "public", "🙌"),
    _cell("C", 13, "盯——", "intense_stare", "趴桌凝视", "专注", "observe", "familiar", "👁️"),
    _cell("C", 14, "不许这样", "firm_boundary", "交叉双臂拒绝", "严肃", "boundary", "public", "🙅"),
    _cell("C", 15, "我晕", "dizzy", "眼冒圈圈发晕", "眩晕", "confuse", "public", "😵‍💫"),
    _cell("C", 16, "贴贴", "warm_hug", "开心拥抱海豚", "温柔亲近", "affection", "close", "🫂"),
)


def build_expression_assets(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if output_dir.name != _ASSET_VERSION or output_dir.is_symlink():
        raise ValueError(f"output directory must end with {_ASSET_VERSION}")
    source_dir = source_dir.resolve()
    validated = _validate_sources(source_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{_ASSET_VERSION}-", dir=output_dir.parent) as tmp:
        staging = Path(tmp) / _ASSET_VERSION
        _create_directories(staging)
        for source in LOCKED_SOURCES:
            shutil.copyfile(source_dir / source.filename, staging / "sources" / source.filename)
        entries: list[dict[str, Any]] = []
        previews: dict[str, Image.Image] = {}
        sheets = {
            source.sheet: Image.open(source_dir / source.filename).convert("RGB")
            for source in LOCKED_SOURCES
            if source.sheet is not None
        }
        try:
            for spec in CELL_SPECS:
                entry, preview = _build_cell(staging, sheets[spec.sheet], spec)
                entries.append(entry)
                previews[spec.coordinate] = preview
            _build_contact_sheets(staging, previews)
            avatar_catalog = _build_avatar_candidates(staging, source_dir, previews)
        finally:
            for image in sheets.values():
                image.close()
            for image in previews.values():
                image.close()

        catalog = {
            "schema_version": 1,
            "catalog_id": "lezhi-expression",
            "catalog_version": "lezhi-expression-v0.3",
            "status": "candidate",
            "persona_id": _PERSONA_ID,
            "persona_version": _PERSONA_VERSION,
            "persona_digest": _PERSONA_DIGEST,
            "source_assets": validated,
            "entries": entries,
            "approval": None,
            "telegram_mapping": None,
        }
        _write_json(staging / "catalog.json", catalog)
        _write_json(staging / "avatar-candidates.json", avatar_catalog)
        output_files = _output_inventory(staging)
        manifest = {
            "schema_version": 1,
            "asset_version": _ASSET_VERSION,
            "status": "candidate",
            "pipeline": {
                "name": "group_llm_agent.asset_pipeline",
                "version": 1,
                "pillow_version": PIL.__version__,
                "grid_order": "A-B-C-row-major-one-based",
                "canvas_size": _CANVAS_SIZE,
            },
            "source_assets": validated,
            "candidate_count": len(entries),
            "catalog_sha256": file_sha256(staging / "catalog.json"),
            "avatar_catalog_sha256": file_sha256(staging / "avatar-candidates.json"),
            "outputs": output_files,
            "approval": None,
        }
        _write_json(staging / "manifest.json", manifest)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        staging.replace(output_dir)
    return cast(
        dict[str, Any],
        json.loads((output_dir / "manifest.json").read_text(encoding="utf-8")),
    )


def _validate_sources(source_dir: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in LOCKED_SOURCES:
        path = source_dir / source.filename
        if not path.is_file() or file_sha256(path) != source.sha256:
            raise ValueError(f"source_digest_mismatch:{source.source_id}")
        with Image.open(path) as image:
            if image.size != source.dimensions or image.mode != source.mode:
                raise ValueError(f"source_shape_mismatch:{source.source_id}")
        result.append(
            {
                "source_id": source.source_id,
                "filename": source.filename,
                "sha256": source.sha256,
                "width": source.dimensions[0],
                "height": source.dimensions[1],
                "mode": source.mode,
                "sheet": source.sheet,
            }
        )
    return result


def _create_directories(root: Path) -> None:
    for relative in (
        "sources",
        "masters",
        "telegram",
        "previews/light",
        "previews/dark",
        "avatars",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)


def _build_cell(
    root: Path, sheet: Image.Image, spec: CellSpec
) -> tuple[dict[str, Any], Image.Image]:
    left = (spec.column - 1) * sheet.width // 4
    right = spec.column * sheet.width // 4
    top = (spec.row - 1) * sheet.height // 4
    bottom = spec.row * sheet.height // 4
    cell = sheet.crop((left, top, right, bottom)).convert("RGBA")
    transparent = _remove_edge_fragments(
        _remove_connected_background(cell),
        clear_top_spill=spec.row in {2, 3},
        clear_left_spill=spec.column > 1,
    )
    if spec.coordinate == "C08":
        alpha = transparent.getchannel("A")
        ImageDraw.Draw(alpha).rectangle((0, 0, alpha.width, 44), fill=0)
        transparent.putalpha(alpha)
    if spec.sheet == "A" and spec.row == 3:
        alpha = transparent.getchannel("A")
        ImageDraw.Draw(alpha).rectangle((0, alpha.height - 20, alpha.width, alpha.height), fill=0)
        transparent.putalpha(alpha)
    master = _fit_transparent_canvas(transparent)
    coordinate = spec.coordinate
    master_relative = f"masters/{coordinate}.png"
    telegram_relative = f"telegram/{coordinate}.webp"
    master_path = root / master_relative
    telegram_path = root / telegram_relative
    master.save(master_path, format="PNG", optimize=True, compress_level=9)
    master.save(telegram_path, format="WEBP", lossless=True, method=6, exact=True)
    light = _composite_preview(master, (247, 250, 255))
    dark = _composite_preview(master, (35, 48, 68))
    light.save(root / "previews" / "light" / f"{coordinate}.png", optimize=True)
    dark.save(root / "previews" / "dark" / f"{coordinate}.png", optimize=True)
    entry = {
        "semantic_id": spec.semantic_id,
        "source": {"sheet": spec.sheet, "row": spec.row, "column": spec.column},
        "visible_text": spec.visible_text,
        "semantics": {
            "action": spec.action,
            "emotion": spec.emotion,
            "interaction_intent": spec.interaction_intent,
            "use_when": _use_when(spec.interaction_intent),
            "avoid_when": _avoid_when(spec.interaction_intent, spec.minimum_relationship),
            "minimum_relationship": spec.minimum_relationship,
            "emoji": spec.emoji,
        },
        "assets": {
            "master_path": master_relative,
            "master_sha256": file_sha256(master_path),
            "telegram_path": telegram_relative,
            "telegram_sha256": file_sha256(telegram_path),
            "width": _CANVAS_SIZE,
            "height": _CANVAS_SIZE,
        },
        "status": "candidate",
        "approval": None,
        "telegram_mapping": None,
    }
    return entry, master.copy()


def _remove_connected_background(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    width, height = image.size
    seed = Image.new("L", image.size, 0)
    seed.putdata(
        [
            255
            if alpha > 0
            and (min(red, green, blue) < 205 or max(red, green, blue) - min(red, green, blue) > 20)
            else 0
            for red, green, blue, alpha in image.getdata()
        ]
    )
    protected_mask = seed.filter(ImageFilter.GaussianBlur(8.0)).point(
        lambda value: 255 if value >= 4 else 0
    )
    protected = list(protected_mask.getdata())
    pixels = cast(Any, image.load())
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(1, height - 1):
        queue.append((0, y))
        queue.append((width - 1, y))
    while queue:
        x, y = queue.popleft()
        offset = y * width + x
        if visited[offset]:
            continue
        visited[offset] = 1
        red, green, blue, alpha = pixels[x, y]
        low = min(red, green, blue)
        high = max(red, green, blue)
        if alpha == 0 or (low >= 205 and high - low <= 20):
            pixels[x, y] = (red, green, blue, alpha if protected[offset] else 0)
            if x:
                queue.append((x - 1, y))
            if x + 1 < width:
                queue.append((x + 1, y))
            if y:
                queue.append((x, y - 1))
            if y + 1 < height:
                queue.append((x, y + 1))
    return image


def _remove_edge_fragments(
    image: Image.Image, *, clear_top_spill: bool, clear_left_spill: bool
) -> Image.Image:
    """Discard only thin disconnected spillover crossing an internal grid boundary."""

    pixels = cast(Any, image.load())
    width, height = image.size
    visited = bytearray(width * height)
    for start_y in range(height):
        for start_x in range(width):
            start_offset = start_y * width + start_x
            if visited[start_offset] or pixels[start_x, start_y][3] <= 16:
                continue
            queue = deque([(start_x, start_y)])
            component: list[tuple[int, int]] = []
            min_x = max_x = start_x
            min_y = max_y = start_y
            while queue:
                x, y = queue.popleft()
                offset = y * width + x
                if visited[offset] or pixels[x, y][3] <= 16:
                    continue
                visited[offset] = 1
                component.append((x, y))
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                if x:
                    queue.append((x - 1, y))
                if x + 1 < width:
                    queue.append((x + 1, y))
                if y:
                    queue.append((x, y - 1))
                if y + 1 < height:
                    queue.append((x, y + 1))
            component_width = max_x - min_x + 1
            component_height = max_y - min_y + 1
            thin_horizontal_edge = (min_y <= 4 or max_y >= height - 5) and component_height <= 12
            thin_vertical_edge = (min_x <= 4 or max_x >= width - 5) and component_width <= 12
            preceding_row_spill = clear_top_spill and max_y <= 56
            preceding_column_spill = clear_left_spill and min_x == 0 and max_x <= 32
            if (
                thin_horizontal_edge
                or thin_vertical_edge
                or preceding_row_spill
                or preceding_column_spill
            ):
                for x, y in component:
                    red, green, blue, _ = pixels[x, y]
                    pixels[x, y] = (red, green, blue, 0)
    return image


def _fit_transparent_canvas(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value > 8 else 0).getbbox()
    if bbox is None:
        raise ValueError("empty_sticker_cell")
    content = image.crop(bbox)
    content.thumbnail((_CONTENT_SIZE, _CONTENT_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (_CANVAS_SIZE, _CANVAS_SIZE), (0, 0, 0, 0))
    offset = ((_CANVAS_SIZE - content.width) // 2, (_CANVAS_SIZE - content.height) // 2)
    canvas.alpha_composite(content, offset)
    return canvas


def _composite_preview(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    background = Image.new("RGBA", image.size, (*color, 255))
    background.alpha_composite(image)
    return background.convert("RGB")


def _build_contact_sheets(root: Path, previews: dict[str, Image.Image]) -> None:
    for sheet in ("A", "B", "C"):
        coordinates = [f"{sheet}{index:02d}" for index in range(1, 17)]
        contact = _contact_sheet(coordinates, previews, columns=4)
        contact.save(root / "previews" / f"contact-{sheet.lower()}.png", optimize=True)
        contact.close()
    all_coordinates = [spec.coordinate for spec in CELL_SPECS]
    contact = _contact_sheet(all_coordinates, previews, columns=8)
    contact.save(root / "previews" / "contact-all.png", optimize=True)
    contact.close()


def _contact_sheet(
    coordinates: list[str], previews: dict[str, Image.Image], *, columns: int
) -> Image.Image:
    tile = 256
    label_height = 28
    rows = (len(coordinates) + columns - 1) // columns
    contact = Image.new("RGB", (columns * tile, rows * (tile + label_height)), "#eef4fc")
    draw = ImageDraw.Draw(contact)
    font = ImageFont.load_default(size=18)
    for index, coordinate in enumerate(coordinates):
        image = previews[coordinate].copy()
        image.thumbnail((tile, tile), Image.Resampling.LANCZOS)
        x = index % columns * tile
        y = index // columns * (tile + label_height)
        contact.paste(_composite_preview(image, (247, 250, 255)).resize((tile, tile)), (x, y))
        draw.text((x + 8, y + tile + 4), coordinate, fill="#174f94", font=font)
        image.close()
    return contact


def _build_avatar_candidates(
    root: Path, source_dir: Path, previews: dict[str, Image.Image]
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    with Image.open(source_dir / "character.png") as character:
        default = character.convert("RGB").crop((310, 35, 655, 380))
        default = default.resize((640, 640), Image.Resampling.LANCZOS)
        candidates.append(
            _write_avatar(
                root,
                "lezhi-default",
                default,
                source="visual-source-001:front-head-crop",
                moods=("default",),
            )
        )
    for avatar_id, coordinate, moods in (
        ("lezhi-joyful", "A13", ("joyful", "celebratory")),
        ("lezhi-playful", "B03", ("playful", "mischievous")),
        ("lezhi-pouty", "C07", ("pouty", "mildly_annoyed")),
        ("lezhi-gentle", "A04", ("gentle", "caring")),
    ):
        preview = _composite_preview(previews[coordinate], (255, 255, 255)).resize(
            (640, 640), Image.Resampling.LANCZOS
        )
        candidates.append(
            _write_avatar(
                root,
                avatar_id,
                preview,
                source=f"candidate:{coordinate}",
                moods=moods,
                depends_on_sticker_approval=True,
            )
        )
        preview.close()
    return {
        "schema_version": 1,
        "catalog_id": "lezhi-avatar",
        "catalog_version": "lezhi-avatar-v0.3",
        "status": "candidate",
        "persona_id": _PERSONA_ID,
        "persona_version": _PERSONA_VERSION,
        "persona_digest": _PERSONA_DIGEST,
        "default_avatar_id": "lezhi-default",
        "automatic_rotation": {"enabled": False, "cooldown_hours": 72, "max_changes_7d": 2},
        "candidates": candidates,
        "approval": None,
    }


def _write_avatar(
    root: Path,
    avatar_id: str,
    image: Image.Image,
    *,
    source: str,
    moods: tuple[str, ...],
    depends_on_sticker_approval: bool = False,
) -> dict[str, Any]:
    jpg_relative = f"avatars/{avatar_id}.jpg"
    preview_relative = f"avatars/{avatar_id}-circle.png"
    jpg_path = root / jpg_relative
    preview_path = root / preview_relative
    image.convert("RGB").save(
        jpg_path, format="JPEG", quality=95, subsampling=0, optimize=True, progressive=False
    )
    circle = Image.new("RGBA", image.size, (0, 0, 0, 0))
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse((4, 4, image.width - 5, image.height - 5), fill=255)
    circle.paste(image.convert("RGBA"), (0, 0), mask)
    circle.save(preview_path, format="PNG", optimize=True)
    circle.close()
    return {
        "avatar_id": avatar_id,
        "source": source,
        "image_path": jpg_relative,
        "image_sha256": file_sha256(jpg_path),
        "circle_preview_path": preview_relative,
        "circle_preview_sha256": file_sha256(preview_path),
        "safe_area": "center-circle-90-percent",
        "allowed_moods": list(moods),
        "disabled_when": ["unconfirmed", "cooldown_active", "global_scope_uncertain"],
        "depends_on_sticker_approval": depends_on_sticker_approval,
        "status": "candidate",
        "approval": None,
    }


def _use_when(intent: str) -> list[str]:
    return {
        "greeting": ["轻量问候或重新加入对话"],
        "acknowledge": ["只需简短确认且无需补充事实"],
        "listen": ["成员正在表达感受且需要被倾听"],
        "care": ["熟悉成员需要轻柔关心"],
        "think": ["需要表达正在思考而非给出结论"],
        "approve": ["轻量认可或赞同"],
        "amuse": ["明确的共同笑点或轻松玩笑"],
        "encourage": ["轻量加油或行动鼓励"],
        "apologize": ["需要简短道歉且不会回避补救"],
        "clarify": ["对轻量内容表示疑问"],
        "calm": ["非紧急场景中安抚节奏"],
        "investigate": ["表示将进行查询，后续仍会给文字结果"],
        "celebrate": ["共同完成小目标或轻量好消息"],
        "appreciate": ["感谢成员付出或表达慰问"],
        "sleep": ["自然结束夜间对话"],
        "affection": ["关系明确且双方接受的亲近互动"],
        "tease": ["关系足够且语境明确的友善打趣"],
        "style": ["轻量自我调侃或仪式感"],
        "confidence": ["轻量表达已经掌握"],
        "observe": ["轻量围观或持续关注"],
        "boundary": ["用非攻击方式表达轻度边界"],
        "react": ["非严肃事件中的即时惊讶"],
        "distress": ["夸张但明确是玩笑式的轻量崩溃"],
        "skepticism": ["轻量质疑或难以置信"],
        "confuse": ["轻量表达信息过载或困惑"],
        "rescue": ["夸张式求助而非真实紧急事件"],
    }[intent]


def _avoid_when(intent: str, relationship: str) -> list[str]:
    result = ["事实、步骤、严肃求助或安全场景需要实质文字", "画面或语义匹配不精确"]
    if relationship in {"familiar", "close"}:
        result.append("关系强度不足或成员表达不适")
    if intent in {"tease", "boundary", "distress", "rescue"}:
        result.append("冲突升级、真实痛苦或紧急事件")
    if intent == "affection":
        result.append("亲近互动未获明确语境支持")
    return result


def _output_inventory(root: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "manifest.json":
            continue
        result.append({"path": relative, "sha256": file_sha256(path)})
    return result


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json_bytes(value))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Build locked Lezhi expression candidates")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    manifest = build_expression_assets(arguments.source_dir, arguments.output_dir)
    print(
        "expression_candidates_built "
        f"count={manifest['candidate_count']} "
        f"catalog_sha256={manifest['catalog_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
