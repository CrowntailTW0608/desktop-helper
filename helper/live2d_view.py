"""Live2D 完整模型渲染：離屏 FBO 繪製 -> 讀回 RGBA -> QImage，供 Bubble 疊圖使用。

動作/表情行為由 helper.live2d_characters 的角色設定表驅動，新增角色不需修改此檔案。
"""

import ctypes

from OpenGL.GL import (
    GL_COLOR_ATTACHMENT0,
    GL_FRAMEBUFFER,
    GL_LINEAR,
    GL_RGBA,
    GL_TEXTURE_2D,
    GL_UNSIGNED_BYTE,
    glBindFramebuffer,
    glBindTexture,
    glDeleteFramebuffers,
    glDeleteTextures,
    glFramebufferTexture2D,
    glGenFramebuffers,
    glGenTextures,
    glReadPixels,
    glTexImage2D,
    glTexParameteri,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_MAG_FILTER,
    glViewport,
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QOffscreenSurface, QOpenGLContext, QSurfaceFormat

import live2d.v3 as live2d

from helper.live2d_characters import CHARACTERS, model_path


class Live2DRenderer:
    """一顆模型的離屏渲染器。每次呼叫 render_frame() 回傳當前畫面的 QImage（RGBA，含真實 alpha）。"""

    def __init__(self, character_id: str, width: int, height: int, scale: float = 1.0):
        self.width = width
        self.height = height
        self._character = CHARACTERS[character_id]
        self._idle_pos = 0
        self._motion_gen = 0
        self._loop_motion = None  # (group, index, priority)：目前需要手動維持循環播放的動作
        self._sticky_gen = None  # sticky 動作等待下個事件期間，用來讓 _repeat_sticky_motion 知道是否已被取代

        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        self._surface = QOffscreenSurface()
        self._surface.setFormat(fmt)
        self._surface.create()

        self._ctx = QOpenGLContext()
        self._ctx.setFormat(fmt)
        self._ctx.create()
        self._ctx.makeCurrent(self._surface)

        live2d.init()
        live2d.glInit()

        self._fbo = glGenFramebuffers(1)
        self._tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self._tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self._tex, 0)
        glViewport(0, 0, width, height)

        self.model = live2d.LAppModel()
        self.model.LoadModelJson(model_path(character_id))
        self.model.Resize(width, height)
        self.model.SetScale(scale)

        self._expressions = [e for e in self.model.GetExpressionIds() if e.strip() not in ("bl", "anyazZZ")]

        self.start_idle()

    def set_scale(self, scale: float) -> None:
        self.model.SetScale(scale)

    def look_at(self, x: float, y: float) -> None:
        """讓角色頭部/眼睛注視座標 (x, y)，範圍 -1..1（左下為 -1,-1，右上為 1,1）。

        model.Drag() 只會把座標存進底層 dragManager，這個 wrapper 的 Update() 並未
        像官方 C++ sample 一樣把它套用到 ParamAngleX/ParamEyeBallX 等參數，所以要在
        Update() 之後、Draw() 之前自己疊加這幾個標準參數（數值比例沿用官方 sample）。
        """
        self._look_x, self._look_y = x, y

    def _apply_look_at(self) -> None:
        x, y = getattr(self, "_look_x", 0.0), getattr(self, "_look_y", 0.0)
        self.model.AddParameterValue("ParamAngleX", x * 30)
        self.model.AddParameterValue("ParamAngleY", y * 30)
        self.model.AddParameterValue("ParamAngleZ", x * y * 10)
        self.model.AddParameterValue("ParamBodyAngleX", x * 10)
        self.model.AddParameterValue("ParamEyeBallX", x)
        self.model.AddParameterValue("ParamEyeBallY", y)

    def _start_motion(self, group: str, index: int, priority_name: str, on_finish=None) -> None:
        # 素材動作皆 Loop=True 永不 finish，優先權判斷（見 Cubism 官方 SDK 行為）永遠不會自然
        # 釋放，導致同優先權（含 FORCE）後續動作全被判定「priority too low」；先清空再換動作。
        # 注意：onFinish 是 model.Update() 內部同步呼叫的，此處 on_finish 絕不可直接呼叫
        # start_idle()/StartMotion() 等會再次操作 model 的方法（reentrancy 會讓底層狀態
        # 損毀、過一段時間就 crash）——一律用 QTimer.singleShot(0, ...) 延到下一輪事件迴圈執行。
        self.model.StopAllMotions()
        priority = getattr(live2d.MotionPriority, priority_name)
        self.model.StartMotion(group, index, priority, onFinishMotionHandler=on_finish)

    def set_expression(self, name: str) -> None:
        if name in self._expressions:
            self.model.SetExpression(name)

    def reset_expression(self) -> None:
        self.model.ResetExpressions()

    def start_idle(self) -> None:
        """依角色設定的 idle 清單輪流播放；清單只有一筆時等同單一待機動作反覆播放。

        優先權固定用 FORCE：Cubism 的優先權保留機制是單向的——StopAllMotions() 不會重置
        保留優先權，同級（FORCE→FORCE）可以蓋過，但由高（FORCE）切回低（IDLE）永遠會被
        判定「priority is too low」而失敗。所有切換都經過我們自己的 Python 狀態機控管，
        底層優先權分級已無意義，故統一用 FORCE 避免這個方向性限制。
        """
        self._loop_motion = None
        self._sticky_gen = None
        idle_list = self._character["idle"]
        if not idle_list:
            return
        entry = idle_list[self._idle_pos % len(idle_list)]
        self._idle_pos += 1
        self._start_motion(
            entry["group"], entry["index"], "FORCE",
            on_finish=lambda *_: QTimer.singleShot(0, self.start_idle),
        )

    # ── Trigger 事件反應：由角色設定的 reactions 表驅動 ────────────────────

    def react(self, event: str, tool_name: str = "") -> None:
        reactions = self._character["reactions"]
        action = reactions.get(f"{event}:{tool_name}") if tool_name else None
        if action is None:
            action = reactions.get(event)
        if action is None:
            return
        if action.get("reset"):
            self.reset_expression()
        if action.get("idle"):
            self.start_idle()
            return
        if "expression" in action:
            self.set_expression(action["expression"])
        motion = action.get("motion")
        if motion:
            self._motion_gen += 1
            gen = self._motion_gen
            group, index = motion.get("group", ""), motion["index"]
            priority = motion.get("priority", "FORCE")
            hold = motion.get("hold")
            sticky = motion.get("sticky", False)  # True：等下一個 react() 事件才離開，不會自己回 idle
            repeat = motion.get("repeat")  # sticky 專用：每隔幾秒重播一次，通常填該動作 Meta.Duration
            self._loop_motion = None if (hold or sticky) else (group, index, priority)
            self._sticky_gen = gen if sticky else None
            self._start_motion(
                group, index, priority,
                on_finish=None if sticky else lambda *_: QTimer.singleShot(0, lambda: self._on_motion_naturally_finished(gen)),
            )
            if hold:
                # 素材動作多為 Loop=True，永遠不會觸發 onFinish，需靠計時器強制回 idle。
                QTimer.singleShot(int(hold * 1000), lambda: self._on_hold_expired(gen))
            if sticky and repeat:
                QTimer.singleShot(
                    int(repeat * 1000),
                    lambda: self._repeat_sticky_motion(gen, group, index, priority, repeat),
                )

    def _repeat_sticky_motion(self, gen: int, group: str, index: int, priority: str, repeat: float) -> None:
        """sticky 動作等待期間持續重播，直到下個事件（PostToolUse 等）呼叫 start_idle()/
        另一個 react() 蓋過 self._sticky_gen 為止。"""
        if gen != self._sticky_gen:
            return
        self._start_motion(group, index, priority, on_finish=None)
        QTimer.singleShot(int(repeat * 1000), lambda: self._repeat_sticky_motion(gen, group, index, priority, repeat))

    def _on_motion_naturally_finished(self, gen: int) -> None:
        """有些素材雖標 Loop=True，播完一輪仍會觸發一次 onFinish；若這個動作被設計為
        持續播放到下個事件蓋過（self._loop_motion 已設定），就不能在這裡搶先切回 idle，
        否則會跟 _keep_loop_motion_alive() 的重播互相打架，導致動作提早結束。"""
        if gen == self._motion_gen and self._loop_motion is None:
            self.start_idle()

    def _on_hold_expired(self, gen: int) -> None:
        if gen == self._motion_gen:
            self.start_idle()

    def _keep_loop_motion_alive(self) -> None:
        """部分素材標示 Loop=True 但底層播完後不會自動重播、也不觸發 onFinish，
        只會停在最後一幀；每幀檢查一次，播完就手動重新 StartMotion 維持循環，
        直到被 idle / 下個事件（清空 self._loop_motion）取代。"""
        if self._loop_motion is None:
            return
        if self.model.IsMotionFinished():
            group, index, priority = self._loop_motion
            self._start_motion(
                group, index, priority,
                on_finish=lambda *_: QTimer.singleShot(0, self.start_idle),
            )

    def render_frame(self) -> QImage:
        self._ctx.makeCurrent(self._surface)
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo)
        glViewport(0, 0, self.width, self.height)
        live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
        self.model.Update()
        self._keep_loop_motion_alive()
        self._apply_look_at()
        self.model.Draw()
        raw = glReadPixels(0, 0, self.width, self.height, GL_RGBA, GL_UNSIGNED_BYTE)
        buf = raw if isinstance(raw, (bytes, bytearray)) else ctypes.string_at(raw, self.width * self.height * 4)
        img = QImage(buf, self.width, self.height, QImage.Format_RGBA8888)
        return img.mirrored(False, True).copy()

    def dispose(self) -> None:
        glDeleteFramebuffers(1, [self._fbo])
        glDeleteTextures(1, [self._tex])
        live2d.dispose()
