from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime

from group_llm_agent.temporal import (
    AutomationGroupTimezoneProvider,
    TemporalContextError,
    TemporalContextFactory,
    TemporalSession,
    TimezoneSelection,
    validate_iana_timezone,
)


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self.values = list(values)

    def __call__(self) -> datetime:
        if not self.values:
            raise RuntimeError("clock exhausted")
        return self.values.pop(0)


@dataclass(frozen=True)
class Config:
    timezone: object


class ConfigReader:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def get_config(self, *, chat_id: str) -> object | None:
        return self.value


class TemporalContextTests(unittest.TestCase):
    def test_shanghai_snapshot_has_exact_local_fields(self) -> None:
        instant = datetime(2026, 8, 11, 4, 34, 20, tzinfo=UTC)
        context = TemporalContextFactory(clock=lambda: instant).sample(
            group_timezone="Asia/Shanghai"
        )

        self.assertEqual("2026-08-11T04:34:20+00:00", context.as_prompt_data()["current_utc"])
        self.assertEqual("2026-08-11T12:34:20+08:00", context.as_prompt_data()["current_local"])
        self.assertEqual("+08:00", context.utc_offset)
        self.assertEqual("2026-08-11", context.local_date)
        self.assertEqual(2, context.local_weekday_number)
        self.assertEqual("Tuesday", context.local_weekday_name)
        self.assertTrue(context.context_id.startswith("time:v1:"))

    def test_new_york_uses_iana_dst_rules(self) -> None:
        winter = TemporalContextFactory(
            clock=lambda: datetime(2026, 1, 15, 12, tzinfo=UTC)
        ).sample(group_timezone="America/New_York")
        summer = TemporalContextFactory(
            clock=lambda: datetime(2026, 7, 15, 12, tzinfo=UTC)
        ).sample(group_timezone="America/New_York")

        self.assertEqual("-05:00", winter.utc_offset)
        self.assertEqual(7, winter.current_local.hour)
        self.assertEqual("-04:00", summer.utc_offset)
        self.assertEqual(8, summer.current_local.hour)

    def test_session_resamples_and_allows_one_current_turn_override(self) -> None:
        session = TemporalSession(
            group_timezone="Asia/Shanghai",
            factory=TemporalContextFactory(
                clock=SequenceClock(
                    datetime(2026, 8, 11, 4, 30, tzinfo=UTC),
                    datetime(2026, 8, 11, 4, 40, tzinfo=UTC),
                )
            ),
        )
        first = session.sample_for_model_call()
        session.select_answer_timezone("America/New_York")
        second = session.sample_for_model_call()

        self.assertNotEqual(first.context_id, second.context_id)
        self.assertEqual("Asia/Shanghai", first.answer_timezone)
        self.assertEqual("America/New_York", second.answer_timezone)
        self.assertEqual(TimezoneSelection.WRITER_EXPLICIT_OVERRIDE, second.timezone_selection)
        self.assertEqual(2, session.model_call_ordinal)
        with self.assertRaisesRegex(TemporalContextError, "timezone_selection_already_used"):
            session.select_answer_timezone("Asia/Tokyo")

    def test_occurrence_metadata_has_utc_and_target_local_time(self) -> None:
        context = TemporalContextFactory(
            clock=lambda: datetime(2026, 8, 11, 12, tzinfo=UTC)
        ).sample(group_timezone="Asia/Shanghai")
        data = context.occurrence_data(datetime(2026, 8, 10, 15, 30, tzinfo=UTC))

        self.assertEqual("2026-08-10T15:30:00+00:00", data["occurred_at_utc"])
        self.assertEqual("2026-08-10T23:30:00+08:00", data["occurred_at_target_local"])
        self.assertEqual("Asia/Shanghai", data["occurred_timezone"])

    def test_invalid_clock_and_timezone_fail_closed(self) -> None:
        with self.assertRaisesRegex(TemporalContextError, "invalid_clock"):
            TemporalContextFactory(clock=lambda: datetime(2026, 8, 11)).sample(
                group_timezone="Asia/Shanghai"
            )
        for value in ("+08:00", "Mars/Olympus", "", "Asia/ Shanghai"):
            with self.subTest(value=value), self.assertRaises(TemporalContextError):
                validate_iana_timezone(value)

    def test_group_timezone_provider_uses_existing_config_or_default(self) -> None:
        self.assertEqual(
            "Asia/Shanghai",
            AutomationGroupTimezoneProvider(ConfigReader(None)).timezone_for(chat_id="group-a"),
        )
        self.assertEqual(
            "America/New_York",
            AutomationGroupTimezoneProvider(
                ConfigReader(Config(timezone="America/New_York"))
            ).timezone_for(chat_id="group-a"),
        )
        with self.assertRaisesRegex(TemporalContextError, "invalid_group_timezone"):
            AutomationGroupTimezoneProvider(ConfigReader(Config(timezone="broken"))).timezone_for(
                chat_id="group-a"
            )


if __name__ == "__main__":
    unittest.main()
