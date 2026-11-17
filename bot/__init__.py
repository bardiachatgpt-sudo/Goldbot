try:                                    # محور قیمت همیشه قیمت کامل (نه «+1.1» و عدد نسبی)
    import matplotlib
    matplotlib.rcParams["axes.formatter.useoffset"] = False
except Exception:
    pass
