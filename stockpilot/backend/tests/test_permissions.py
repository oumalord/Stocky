from django.test import TestCase

from .helpers import client_for, main_location, make_branch_location, make_org, make_product, make_user, post_move
from rest_framework.test import APIClient


class PermissionTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org()
        self.product = make_product(self.org)
        self.loc = main_location(self.org)

    def test_unauthenticated_is_rejected(self):
        self.assertIn(APIClient().get("/api/v1/products/").status_code, (401, 403))

    def test_counter_can_view_but_not_manage_or_post(self):
        c = client_for(make_user(self.org, "counter", "c@a.test"), self.org)
        self.assertEqual(c.get("/api/v1/products/").status_code, 200)
        self.assertEqual(c.post("/api/v1/products/", {"sku": "X", "name": "x", "base_uom": str(self.product.base_uom_id)}, format="json").status_code, 403)
        self.assertEqual(c.get("/api/v1/movements/").status_code, 403)
        self.assertEqual(post_move(c, self.product, self.loc, 1, "RECEIPT", "k1").status_code, 403)
        self.assertEqual(c.get("/api/v1/audit-events/").status_code, 403)

    def test_auditor_reads_audit_but_cannot_post(self):
        c = client_for(make_user(self.org, "auditor", "au@a.test"), self.org)
        self.assertEqual(c.get("/api/v1/audit-events/").status_code, 200)
        self.assertEqual(post_move(c, self.product, self.loc, 1, "RECEIPT", "k2").status_code, 403)

    def test_adjustment_type_cannot_be_posted_directly(self):
        c = client_for(self.owner, self.org)
        self.assertEqual(post_move(c, self.product, self.loc, 5, "ADJUSTMENT", "k3").status_code, 400)
        self.assertEqual(post_move(c, self.product, self.loc, 5, "REVERSAL", "k4").status_code, 400)

    def test_branch_restricted_member_cannot_touch_other_branches(self):
        branch_a, loc_a = make_branch_location(self.org, "BA")
        _, loc_b = make_branch_location(self.org, "BB")
        mgr = make_user(self.org, "branch_manager", "m@a.test", branches=[branch_a])
        c = client_for(mgr, self.org)
        self.assertEqual(post_move(c, self.product, loc_a, 3, "RECEIPT", "b1").status_code, 201)
        self.assertEqual(post_move(c, self.product, loc_b, 3, "RECEIPT", "b2").status_code, 403)
        codes = {r["code"] for r in c.get("/api/v1/locations/").data["results"]}
        self.assertEqual(codes, {"BA-LOC"})

    def test_registration_login_and_me(self):
        c = APIClient()
        res = c.post("/api/v1/auth/register/", {"organisation_name": "Fresh Ltd", "full_name": "Fay",
                     "email": "fay@fresh.test", "password": "Correct-horse-battery-9"}, format="json")
        self.assertEqual(res.status_code, 201)
        c.post("/api/v1/auth/logout/")
        bad = c.post("/api/v1/auth/login/", {"email": "fay@fresh.test", "password": "wrong"}, format="json")
        self.assertEqual(bad.status_code, 401)
        ok = c.post("/api/v1/auth/login/", {"email": "fay@fresh.test", "password": "Correct-horse-battery-9"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(c.get("/api/v1/auth/me/").data["memberships"][0]["role"], "owner")
        self.assertEqual(c.get("/api/v1/products/").status_code, 200)

    def test_weak_password_rejected_at_registration(self):
        res = APIClient().post("/api/v1/auth/register/", {"organisation_name": "W", "full_name": "W",
                               "email": "w@w.test", "password": "12345678"}, format="json")
        self.assertEqual(res.status_code, 400)
