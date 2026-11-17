import logic as L

def fresh():
    L.reset()

def test_paid_late_cancel_refund_minus_charge():
    fresh()
    oid = L.place_order(1, 1, paid=True)           # Rs 300 paid
    L.skip_time(oid)
    r = L.cancel_order(oid)
    o = [x for x in L.state()["orders"] if x["id"] == oid][0]
    assert r["late"] and o["refund"] == 210 and o["status"] == "Cancelled"
    assert r["notified"] == 2                       # Abhay + Priya (same area), not Rahul

def test_unpaid_late_cancel_charge_on_next_order():
    fresh()
    oid = L.place_order(1, 1, paid=False)
    L.skip_time(oid)
    L.cancel_order(oid)
    nxt = L.place_order(1, 2, paid=False)           # Paneer Wrap Rs 180 (+90)
    o = [x for x in L.state()["orders"] if x["id"] == nxt][0]
    assert o["amount"] == 270 and o["extra_charge"] == 90
    assert L.state()["stats"]["charges_recovered"] == 90
    nxt2 = L.place_order(1, 2, paid=False)          # charge must not be applied twice
    assert [x for x in L.state()["orders"] if x["id"] == nxt2][0]["amount"] == 180

def test_early_cancel_is_free():
    fresh()
    oid = L.place_order(1, 1, paid=True)
    r = L.cancel_order(oid)
    o = [x for x in L.state()["orders"] if x["id"] == oid][0]
    assert not r["late"] and o["refund"] == 300
    assert L.state()["offers"] == []

def test_claim_rules():
    fresh()
    oid = L.place_order(1, 1, paid=True)
    L.skip_time(oid)
    offer = L.cancel_order(oid)["offer_id"]
    for uid, msg in [(4, "same area"), (1, "cancelled")]:
        try:
            L.claim_offer(offer, uid); assert False
        except L.RuleError as e:
            assert msg in str(e)
    L.claim_offer(offer, 2)                         # Abhay gets it at Rs 210
    try:
        L.claim_offer(offer, 3); assert False       # Priya is too late
    except L.RuleError as e:
        assert "already" in str(e)
    s = L.state()["stats"]
    assert s["meals_rescued"] == 1 and s["food_saved_value"] == 300

def test_cannot_cancel_twice():
    fresh()
    oid = L.place_order(1, 1, paid=True)
    L.cancel_order(oid)
    try:
        L.cancel_order(oid); assert False
    except L.RuleError:
        pass

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)
