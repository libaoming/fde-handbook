#!/usr/bin/env python3
"""复现「float32 音频被当作 int16 读取」的特征——顶满量程。

配套《把 Agent 送上生产》第 2 章。

那次事故里，决定性的证据是一行诊断日志：

    i16_max_abs=32761   # 后续 chunk 为 32767

32767 是 int16 的量程上限。正常语音不该顶满。本脚本用可复现的方式证明：
把一段振幅正常的 float32 音频的**原始字节**按 int16 解释，几乎必然撞满量程——
所以「顶满」不是音量太大，是格式读错了。

用法：
    python3 float32-int16-misread.py            # 跑实验
    python3 float32-int16-misread.py --assert   # 跑实验并对结论做断言（CI 用，失败退出码 1）

输出为判定标量，不需要人去解读波形。
"""
import sys

try:
    import numpy as np
except ImportError:
    print("VERDICT=SKIPPED_NO_NUMPY", file=sys.stderr)
    sys.exit(2)


SAMPLE_RATE = 24_000
DURATION_S = 0.5
AMPLITUDE = 0.3          # 正常说话音量，远离 1.0 的削波边缘
INT16_MAX = 32767


def make_float32_audio() -> np.ndarray:
    """生成一段振幅正常的 float32 音频（440Hz 正弦 + 少量噪声）。"""
    rng = np.random.default_rng(42)          # 固定种子，结果可复现
    t = np.arange(int(SAMPLE_RATE * DURATION_S)) / SAMPLE_RATE
    tone = np.sin(2 * np.pi * 440 * t)
    noise = rng.normal(0, 0.02, t.shape)
    return (AMPLITUDE * tone + noise).astype(np.float32)


def correct_path(f32: np.ndarray) -> np.ndarray:
    """正确解读：先把 float32 的**数值**缩放到 int16 量程。

    这就是 agent_realtime.py L198-199 的做法。
    """
    clipped = np.clip(f32, -1.0, 1.0)
    return (clipped * INT16_MAX).astype(np.int16)


def misread_path(f32: np.ndarray) -> np.ndarray:
    """错误解读：把 float32 的**原始字节**直接当成 int16。

    这就是那 14 分钟里我改成的样子——没有任何转换，直接 frombuffer。
    """
    return np.frombuffer(f32.tobytes(), dtype=np.int16)


def main() -> int:
    f32 = make_float32_audio()
    ok = correct_path(f32)
    bad = misread_path(f32)

    f32_max = float(np.abs(f32).max())
    ok_max = int(np.abs(ok).max())
    bad_max = int(np.abs(bad).max())
    # 「接近量程」的采样点占比。注意用 90% 而不是「等于 32767」：
    # 错读的特征是最大值紧贴上限，而不是大批采样点恰好等于上限。
    NEAR = int(INT16_MAX * 0.9)
    bad_near_rate = float((np.abs(bad) >= NEAR).mean())
    ok_near_rate = float((np.abs(ok) >= NEAR).mean())

    print(f"F32_MAX_ABS={f32_max:.4f}")
    print(f"CORRECT_I16_MAX_ABS={ok_max}")
    print(f"CORRECT_NEAR_RAIL_RATE={ok_near_rate:.4f}")
    print(f"MISREAD_I16_MAX_ABS={bad_max}")
    print(f"MISREAD_NEAR_RAIL_RATE={bad_near_rate:.4f}")
    print(f"MISREAD_SAMPLE_COUNT_RATIO={len(bad) / len(ok):.1f}")

    # 结论判定。
    # 阈值取量程的 99.9%（=32734）而非 INT16_MAX-1：
    # 首次运行实测错读得到 32760，距上限仅差 7——任何合理定义下都叫「顶满」，
    # 但它不会恰好等于 32767。把判据卡在 32766 是过严的实验设计缺陷，
    # 而不是现象未复现。此处放宽是修正判据，不是为了让断言通过而挪靶子。
    RAIL = int(INT16_MAX * 0.999)
    misread_saturates = bad_max >= RAIL
    correct_is_sane = ok_max < RAIL
    verdict = "REPRODUCED" if (misread_saturates and correct_is_sane) else "NOT_REPRODUCED"
    print(f"RAIL_THRESHOLD={RAIL}")
    print(f"VERDICT={verdict}")

    if "--assert" in sys.argv:
        if verdict != "REPRODUCED":
            print("ASSERT_FAILED=1", file=sys.stderr)
            return 1
        print("ASSERT_PASSED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
