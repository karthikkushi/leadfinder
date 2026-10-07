"""Run: .venv/bin/python -m tests.test_research"""
from leadfinder.brief import rule_problems
from leadfinder.research import IG_RE, to_int

m = IG_RE.search("4,813 Followers, 300 Following, 491 Posts - Experia (@experiaskinclinic) on Instagram")
assert m and to_int(m.group(1)) == 4813 and m.group(5) == "experiaskinclinic"
assert to_int("132K") == 132000 and to_int("1.2M") == 1200000

ok = {"call": "yes", "headline": "h", "why_call": ["x [F1]"], "sell": {"main": "m"}, "opening": "o", "questions": ["q"],
      "pitch": "p", "objections": [{}], "whatsapp": "Hi, rated 4.9. Shall I?"}
assert rule_problems(ok, "[F1] Justdial: rated 4.9") == []
assert any("4.8" in p for p in rule_problems(ok | {"pitch": "rated 4.8"}, "[F1] Justdial: rated 4.9"))
assert rule_problems({"call": "no", "headline": "chain", "why_call": ["x"]}, "") == []
print("ok")
