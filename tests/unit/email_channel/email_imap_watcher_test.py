from unittest.mock import MagicMock

import pytest

from email_channel.email_imap_watcher import EmailImapWatcher


class TestEmailImapWatcher:
    @pytest.mark.asyncio
    async def test_start_creates_task(self, watcher: EmailImapWatcher) -> None:
        await watcher.start()
        assert watcher._task is not None
        assert not watcher._task.done()
        await watcher.stop()

    @pytest.mark.asyncio
    async def test_start_does_not_create_duplicate_task(
        self, watcher: EmailImapWatcher
    ) -> None:
        await watcher.start()
        task1 = watcher._task
        await watcher.start()
        task2 = watcher._task
        assert task1 is task2
        await watcher.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_loop(self, watcher: EmailImapWatcher) -> None:
        await watcher.start()
        assert watcher._task is not None
        await watcher.stop()
        assert watcher._task is None

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, watcher: EmailImapWatcher) -> None:
        await watcher.stop()
        assert watcher._task is None

    @pytest.mark.asyncio
    async def test_run_loop_polls_until_stopped(
        self, mock_processor: MagicMock, watcher: EmailImapWatcher
    ) -> None:
        call_count = 0

        async def fake_poll() -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                watcher._stopping.set()

        mock_processor.poll_once.side_effect = fake_poll

        await watcher.start()
        if watcher._task:
            await watcher._task

        assert call_count >= 3

    @pytest.mark.asyncio
    async def test_run_loop_handles_poll_exceptions(
        self, mock_processor: MagicMock, watcher: EmailImapWatcher
    ) -> None:
        poll_count = 0

        async def failing_poll() -> None:
            nonlocal poll_count
            poll_count += 1
            if poll_count == 1:
                raise RuntimeError("poll error")
            watcher._stopping.set()

        mock_processor.poll_once.side_effect = failing_poll

        await watcher.start()
        if watcher._task:
            await watcher._task

        assert poll_count >= 2
