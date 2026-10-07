import asyncio
import copy
import json
import unittest
from unittest.mock import Mock
from remote.collector import demo_frame
from remote.recovery import CaptureState, AckWindow


class CaptureRecoveryTests(unittest.TestCase):
    def test_inconsistent_copy_does_not_change_session_or_rewind_time(self):
        state=CaptureState(False,0)
        state.update(demo_frame(10),0)
        session=state.session_id
        self.assertIsNone(state.update(None,.1))
        missing=state.update(None,.7)
        self.assertEqual(missing['gameTime'],10)
        self.assertEqual(missing['status'],'waitingForGame')
        state.update(demo_frame(11),.8)
        self.assertEqual(state.session_id,session)

    def test_stale_garage_mapping_is_reopened_without_network_restart(self):
        state=CaptureState(False,0);reader=Mock()
        sample=demo_frame(10);sample['status']='garage'
        state.update(copy.deepcopy(sample),0,reader)
        state.update(copy.deepcopy(sample),5.1,reader)
        reader.close.assert_called_once()
        state.update(copy.deepcopy(sample),5.2,reader)
        reader.close.assert_called_once()
        sample['status']='live';sample['gameTime']=11
        self.assertEqual(state.update(sample,5.3,reader)['status'],'live')

    def test_real_session_change_and_rewind_still_reset_session(self):
        state=CaptureState(False,0)
        state.update(demo_frame(10),0);old=state.session_id
        state.update(demo_frame(9),1)
        self.assertNotEqual(old,state.session_id)
        old=state.session_id;sample=demo_frame(10);sample['sourceSession']='new-game-session'
        state.update(sample,2)
        self.assertNotEqual(old,state.session_id)


class AckTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_in_flight_then_ack_releases_capture_and_close_wakes_waiter(self):
        queue=asyncio.Queue()
        window=AckWindow(Mock(recv=queue.get));window.start()
        try:
            window.sent(10);window.sent(11)
            ready=asyncio.create_task(window.ready());await asyncio.sleep(.01)
            self.assertFalse(ready.done())
            await queue.put(json.dumps({'type':'ack','seq':10}))
            await asyncio.wait_for(ready,.5)
            self.assertEqual(list(window.pending),[11])
            window.sent(12)
            ready=asyncio.create_task(window.ready())
            await queue.put(json.dumps({'type':'ack','seq':99}))
            with self.assertRaises(RuntimeError):await asyncio.wait_for(ready,.5)
        finally:await window.close()


if __name__=='__main__':unittest.main()
