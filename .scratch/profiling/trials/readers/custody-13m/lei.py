def ok(s):
    if not s or len(s)!=20 or not s.isalnum(): return False
    n=''.join(str(int(ch,36)) for ch in s.upper())
    return int(n)%97==1
