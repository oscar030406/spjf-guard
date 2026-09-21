import sys
sys.dont_write_bytecode = True


def head_rule(a, s, pred, k, B):
    """Literal 'if over[head] >= B serve head, else smallest prediction'."""
    n = len(a)
    end = [None] * k; sjob = [-1] * k; waiting = []
    start = [-1] * n; comp = [-1] * n; chw = [0] * n
    nxt = 0; done = 0; t = a[0]
    while done < n:
        for r in range(k):
            if end[r] == t:
                j = sjob[r]; comp[j] = t; chw[j] = s[j]
                end[r] = None; sjob[r] = -1; done += 1
        while nxt < n and a[nxt] == t:
            waiting.append(nxt); nxt += 1
        while waiting and (None in end):
            head = min(waiting)
            over = sum(chw[r] for r in range(head + 1, n))
            pick = head if over >= B else min(waiting, key=lambda q: (pred[q], q))
            r = end.index(None)
            end[r] = t + s[pick]; sjob[r] = pick; start[pick] = t
            waiting.remove(pick)
        nt = None
        for e in end:
            if e is not None and (nt is None or e < nt):
                nt = e
        if nxt < n and (nt is None or a[nxt] < nt):
            nt = a[nxt]
        if nt is None:
            break
        t = nt
    return start
