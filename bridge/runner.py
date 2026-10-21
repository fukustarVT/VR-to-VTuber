import asyncio
import time

import bridge.state as state
from bridge.head import poll_head
from bridge.osc import advertise, open_vd_map, serve_http, serve_osc
from bridge.outputs import ifacial, vtube
from bridge.settings import PRESETS, ensure_loaded


async def _stop_task(task):
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def output_supervisor():
    task = None
    current = None
    try:
        while not state.stop_event.is_set():
            dest = state.destination
            if dest != current:
                await _stop_task(task)
                task = None
                current = dest
                state.status["output"] = PRESETS[dest]["waiting"]
                print(f"Output: {PRESETS[dest]['title']}", flush=True)
                session = vtube.session if dest == "vts" else ifacial.session
                task = asyncio.create_task(session())
            elif task is not None and task.done():
                await asyncio.sleep(0.5)
                if state.stop_event.is_set() or state.destination != current:
                    continue
                session = vtube.session if current == "vts" else ifacial.session
                task = asyncio.create_task(session())
            await asyncio.sleep(0.1)
    finally:
        await _stop_task(task)


async def neck_loop():
    period = 1.0 / 60.0
    next_tick = time.monotonic()
    while not state.stop_event.is_set():
        poll_head()
        ready = str(state.status["headset"]).startswith("Connected")
        step = period if ready else 0.4
        next_tick += step
        now = time.monotonic()
        if next_tick < now:
            next_tick = now
        else:
            await asyncio.sleep(next_tick - now)


async def run():
    loop = asyncio.get_running_loop()
    transport = await serve_osc(loop)
    print("Look forward. Quit VRCFaceTracking and open it again so it loads the new shapes.", flush=True)
    state.status["detail"] = "Look forward. Quit VRCFaceTracking and open it again."
    neck_task = asyncio.create_task(neck_loop())
    out_task = asyncio.create_task(output_supervisor())
    try:
        ticks = 0
        while not state.stop_event.is_set():
            await asyncio.sleep(0.5)
            ticks += 1
            state.status["tracking"] = "Connected" if state.packets else "Waiting for VRCFaceTracking"
            if ticks % 4:
                continue
            print(
                f"packets={state.packets} eye=({state.smooth['EyeLeftX']:.2f},{state.smooth['EyeLeftY']:.2f}) "
                f"open={state.smooth['EyeOpenLeft']:.2f} mouth={state.smooth['MouthOpen']:.2f} "
                f"smile={state.smooth['MouthSmile']:.2f} brow={state.smooth['Brows']:.2f} "
                f"head=({state.smooth['FaceAngleX']:.1f},{state.smooth['FaceAngleY']:.1f},{state.smooth['FaceAngleZ']:.1f})",
                flush=True,
            )
    finally:
        neck_task.cancel()
        out_task.cancel()
        transport.close()


def main():
    import threading

    ensure_loaded()
    state.stop_event.clear()
    state.status["headset"] = "Waiting for tracking"
    state.status["source"] = ""
    state.status["tracking"] = "Waiting for VRCFaceTracking"
    state.status["output"] = PRESETS[state.destination]["waiting"]
    httpd = None
    zc = None
    failed = None
    try:
        httpd = serve_http()
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        open_vd_map()
        zc = advertise()
        asyncio.run(run())
    except Exception as exc:
        failed = exc
        if not state.stop_event.is_set():
            print(f"Could not start ({exc}).", flush=True)
    finally:
        if zc is not None:
            zc.close()
        if httpd is not None:
            httpd.shutdown()
        state.status["headset"] = "Waiting for tracking"
        state.status["source"] = ""
        state.status["tracking"] = "Waiting for VRCFaceTracking"
        state.status["output"] = PRESETS[state.destination]["waiting"]
        if failed is not None and not state.stop_event.is_set():
            state.status["detail"] = "Could not start. The log in the console has the reason."
        else:
            state.status["detail"] = "Stopped."


if __name__ == "__main__":
    main()
