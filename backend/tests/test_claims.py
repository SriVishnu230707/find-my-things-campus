"""Claims workflow, privacy, contention, and archival HTTP regressions."""

from concurrent.futures import ThreadPoolExecutor

import test_api


class ClaimsAPI(test_api.ReportAPI):
    def scenario(self, suffix):
        _, student = self.account(suffix)
        code, item, _ = self.request(
            "POST", "/items", {**test_api.REPORT, "type": "found"}
        )
        self.assertEqual(code, 201)
        code, claim, _ = self.request(
            "POST",
            f"/items/{item['id']}/claims",
            {"evidence": "Private identifying marks under the charger"},
            token=student,
        )
        self.assertEqual(code, 201)
        return item, claim, student

    def test_claim_full_handover_and_archival(self):
        item, claim, student = self.scenario("handover")
        path = f"/claims/{claim['id']}"
        code, own, _ = self.request("GET", "/claims/me", token=student)
        self.assertEqual(code, 200)
        self.assertEqual(own[0]["evidence"], claim["evidence"])
        self.assertEqual(
            self.request(
                "PATCH", path + "/decision", {"decision": "approved"}, token=student
            )[0],
            403,
        )
        self.assertEqual(self.request("POST", path + "/handover")[0], 409)
        self.assertEqual(
            self.request("PATCH", path + "/decision", {"decision": "approved"})[0], 200
        )
        self.assertEqual(
            self.request("POST", path + "/handover", token=student)[0], 403
        )
        self.assertEqual(
            self.request("POST", path + "/handover")[1]["status"], "completed"
        )
        self.assertEqual(
            self.request("GET", f"/items/{item['id']}", token=None)[1]["status"],
            "resolved",
        )
        self.assertEqual(self.request("POST", path + "/handover")[0], 409)
        self.assertEqual(self.request("DELETE", f"/items/{item['id']}")[0], 409)
        self.assertEqual(self.request("POST", f"/items/{item['id']}/archive")[0], 200)
        self.assertEqual(self.request("GET", "/items")[1], [])
        self.assertEqual(
            self.request("GET", "/items?archived=true")[1][0]["id"], item["id"]
        )
        self.assertEqual(
            self.request("GET", f"/items/{item['id']}/claims")[1][0]["status"],
            "completed",
        )

    def test_claim_privacy_validation_and_bypass(self):
        item, claim, student = self.scenario("privacy")
        url = f"/items/{item['id']}"
        self.assertEqual(self.request("GET", url + "/claims", token=None)[0], 401)
        self.assertEqual(self.request("GET", url + "/claims", token=student)[0], 403)
        self.assertNotIn("evidence", self.request("GET", url, token=None)[1])
        self.assertEqual(
            self.request("POST", url + "/claims", {"evidence": "valid evidence here"})[
                0
            ],
            403,
        )
        self.assertEqual(
            self.request(
                "POST",
                url + "/claims",
                {"evidence": "valid evidence here"},
                token=student,
            )[0],
            409,
        )
        self.assertEqual(
            self.request("POST", url + "/claims", {"evidence": "short"}, token=student)[
                0
            ],
            422,
        )
        self.assertEqual(
            self.request(
                "POST",
                url + "/claims",
                {"evidence": "valid evidence here", "status": "approved"},
                token=student,
            )[0],
            422,
        )
        for changes in [{"status": "resolved"}, {"type": "lost"}]:
            self.assertEqual(self.request("PATCH", url, changes)[0], 409)
        self.assertEqual(self.request("POST", url + "/archive")[0], 409)
        self.assertEqual(
            self.request("POST", f"/claims/{claim['id']}/withdraw")[0], 403
        )
        self.assertEqual(
            self.request("POST", f"/claims/{claim['id']}/withdraw", token=student)[0],
            200,
        )
        self.assertEqual(self.request("POST", url + "/archive")[0], 200)
        self.assertEqual(self.request("PATCH", url, {"title": "New title"})[0], 409)
        self.assertEqual(
            self.request(
                "POST",
                url + "/claims",
                {"evidence": "valid evidence here"},
                token=student,
            )[0],
            409,
        )

    def test_claim_competing_approval_and_handover(self):
        item, first, _ = self.scenario("first")
        _, second_token = self.account("second")
        second = self.request(
            "POST",
            f"/items/{item['id']}/claims",
            {"evidence": "Different private evidence here"},
            token=second_token,
        )[1]

        def approve(claim):
            return self.request(
                "PATCH", f"/claims/{claim['id']}/decision", {"decision": "approved"}
            )[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(approve, [first, second])), [200, 409])
        claims = self.request("GET", f"/items/{item['id']}/claims")[1]
        winner = next(c for c in claims if c["status"] == "approved")
        self.assertEqual(
            self.request("POST", f"/claims/{winner['id']}/handover")[0], 200
        )
        statuses = [
            c["status"] for c in self.request("GET", f"/items/{item['id']}/claims")[1]
        ]
        self.assertEqual(sorted(statuses), ["completed", "rejected"])

    def test_claim_withdraw_releases_reservation_and_reject(self):
        item, claim, student = self.scenario("withdraw")
        url = f"/claims/{claim['id']}"
        self.assertEqual(
            self.request("PATCH", url + "/decision", {"decision": "approved"})[0], 200
        )
        self.assertEqual(self.request("POST", url + "/withdraw", token=student)[0], 200)
        code, new, _ = self.request(
            "POST",
            f"/items/{item['id']}/claims",
            {"evidence": "New evidence after withdrawal"},
            token=student,
        )
        self.assertEqual(code, 201)
        self.assertEqual(
            self.request(
                "PATCH", f"/claims/{new['id']}/decision", {"decision": "rejected"}
            )[0],
            200,
        )
        self.assertEqual(
            self.request("POST", f"/claims/{new['id']}/withdraw", token=student)[0], 409
        )

    def test_claim_lost_resolved_and_missing(self):
        _, student = self.account("invalid-report")
        item = self.request("POST", "/items", test_api.REPORT)[1]
        url = f"/items/{item['id']}"
        body = {"evidence": "Valid identifying evidence"}
        self.assertEqual(
            self.request("POST", url + "/claims", body, token=student)[0], 409
        )
        self.request("PATCH", url, {"type": "found", "status": "resolved"})
        self.assertEqual(
            self.request("POST", url + "/claims", body, token=student)[0], 409
        )
        self.assertEqual(
            self.request("POST", "/items/999999/claims", body, token=student)[0], 404
        )
        self.assertEqual(self.request("POST", "/claims/999999/handover")[0], 404)

    def test_claim_staff_review_and_restart(self):
        import subprocess
        import sys

        item, claim, student = self.scenario("staff-review")
        _, staff = self.account("claim-staff")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "set-role",
                "--email",
                "claim-staff@example.org",
                "--role",
                "staff",
            ],
            env=self.environment,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.assertEqual(
            self.request("GET", f"/items/{item['id']}/claims", token=staff)[0], 200
        )
        self.assertEqual(
            self.request(
                "PATCH",
                f"/claims/{claim['id']}/decision",
                {"decision": "approved"},
                token=staff,
            )[0],
            200,
        )
        self.stop_server()
        self.start_server()
        self.assertEqual(
            self.request("GET", "/claims/me", token=student)[1][0]["status"], "approved"
        )
        self.assertEqual(
            self.request("POST", f"/claims/{claim['id']}/handover", token=staff)[0], 200
        )

    def test_claim_owner_assignment_preserves_workflow(self):
        import subprocess
        import sys

        item, claim, student = self.scenario("assignment")

        def assign(email):
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.cli",
                    "assign-owner",
                    "--item-id",
                    str(item["id"]),
                    "--email",
                    email,
                ],
                env=self.environment,
                capture_output=True,
                text=True,
            )

        result = assign("assignment@example.org")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.request("GET", f"/items/{item['id']}")[1]["reporter_id"], self.user_id
        )
        self.request("POST", f"/claims/{claim['id']}/withdraw", token=student)
        self.request("POST", f"/items/{item['id']}/archive")
        result = assign("tester@example.org")
        self.assertNotEqual(result.returncode, 0)

    def test_claim_duplicate_submission_race(self):
        _, student = self.account("duplicate-race")
        item = self.request("POST", "/items", {**test_api.REPORT, "type": "found"})[1]

        def submit(_):
            return self.request(
                "POST",
                f"/items/{item['id']}/claims",
                {"evidence": "Private evidence for concurrent submission"},
                token=student,
            )[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(submit, range(2))), [201, 409])


def load_tests(loader, tests, pattern):
    return loader.suiteClass(
        ClaimsAPI(name) for name in ClaimsAPI.__dict__ if name.startswith("test_claim_")
    )
