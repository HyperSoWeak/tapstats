def fmt_compact(n: int) -> str:
    if n >= 1000:
        v = n / 1000
        return f"{v:.1f}k" if v % 1 else f"{int(v)}k"
    return str(n)
