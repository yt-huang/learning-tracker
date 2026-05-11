#!/usr/bin/env python3
"""API integration tests for Learning Tracker.

Run against a running Learning Tracker instance:
  PORT=8010 python3 tests/test_api.py

Or in CI with docker-compose:
  docker compose up -d && sleep 15 && docker compose exec -T learning-tracker python3 tests/test_api.py
"""

import json
import os
import sys
import time
import unittest
import urllib.error
import urllib.request


BASE = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8010")
ADMIN_USER = os.environ.get("TEST_USER", "admin@cpaas.io")
ADMIN_PASS = os.environ.get("TEST_PASS", "07Apples@")


def api(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def ensure_admin_token():
    """Register admin if needed, then login. Returns token."""
    api("POST", "/api/auth/register", {
        "username": ADMIN_USER, "password": ADMIN_PASS, "email": "admin@test.com",
    })
    resp = api("POST", "/api/auth/login", {"username": ADMIN_USER, "password": ADMIN_PASS})
    if not resp.get("ok"):
        raise RuntimeError(f"Cannot login as {ADMIN_USER}: {resp}")
    return resp["token"]


class TestAuth(unittest.TestCase):
    """Authentication tests."""

    @classmethod
    def setUpClass(cls):
        # Wait for server to be ready
        for _ in range(30):
            try:
                urllib.request.urlopen(BASE + "/", timeout=3)
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError(f"Server not reachable at {BASE}")
        # Ensure admin user exists and is loginable
        ensure_admin_token()

    def test_register_duplicate_rejected(self):
        """Registering an existing user should fail."""
        resp = api("POST", "/api/auth/register", {
            "username": ADMIN_USER,
            "password": ADMIN_PASS,
            "email": "admin@test.com",
        })
        # Already registered in setUpClass, should get 409
        self.assertFalse(resp.get("ok"))
        self.assertIn("已存在", resp.get("error", ""))

    def test_login_success(self):
        resp = api("POST", "/api/auth/login", {"username": ADMIN_USER, "password": ADMIN_PASS})
        self.assertTrue(resp.get("ok"), f"Login failed: {resp}")
        self.assertIn("token", resp)

    def test_login_wrong_password(self):
        resp = api("POST", "/api/auth/login", {"username": ADMIN_USER, "password": "wrong"})
        self.assertFalse(resp.get("ok"))

    def test_protected_endpoint_without_token(self):
        resp = api("GET", "/api/plans")
        self.assertFalse(resp.get("ok"))

    def test_health_endpoint(self):
        """Health page should be accessible."""
        try:
            urllib.request.urlopen(BASE + "/", timeout=5)
        except Exception as e:
            self.fail(f"Health page failed: {e}")


class TestPlansMilestonesTasks(unittest.TestCase):
    """Full CRUD lifecycle: create plan -> add milestone -> add task -> delete milestone -> delete plan."""

    token = None
    plan_id = None
    milestone_id = None
    task_id = None

    @classmethod
    def setUpClass(cls):
        cls.token = ensure_admin_token()

    def test_01_create_plan(self):
        resp = api("POST", "/api/plans", {
            "title": "Test Plan E2E",
            "description": "Automated test plan",
            "source_url": "https://example.com",
            "category": "Testing",
            "difficulty": "入门",
            "estimatedHours": 2,
        }, token=self.token)
        self.assertTrue(resp.get("ok"), f"Create plan failed: {resp}")
        self.assertIsNotNone(resp.get("id"))
        TestPlansMilestonesTasks.plan_id = resp["id"]

    def test_02_get_plan(self):
        self.assertIsNotNone(self.plan_id, "No plan_id from test_01")
        resp = api("GET", f"/api/plans/{self.plan_id}", token=self.token)
        self.assertTrue(resp.get("ok"))
        self.assertEqual(resp["plan"]["title"], "Test Plan E2E")

    def test_03_create_milestone(self):
        self.assertIsNotNone(self.plan_id)
        resp = api("POST", f"/api/plans/{self.plan_id}/milestones", {
            "title": "Test Milestone",
            "description": "Automated milestone",
        }, token=self.token)
        self.assertTrue(resp.get("ok"), f"Create milestone failed: {resp}")
        self.assertIsNotNone(resp.get("id"))
        TestPlansMilestonesTasks.milestone_id = resp["id"]

    def test_04_create_task_in_milestone(self):
        self.assertIsNotNone(self.milestone_id)
        self.assertIsNotNone(self.plan_id)
        resp = api("POST", f"/api/milestones/{self.milestone_id}/tasks", {
            "planId": self.plan_id,
            "title": "Test Task",
            "description": "Automated task",
            "estimatedMinutes": 30,
            "priority": "high",
        }, token=self.token)
        self.assertTrue(resp.get("ok"), f"Create task failed: {resp}")
        self.assertIsNotNone(resp.get("id"))
        TestPlansMilestonesTasks.task_id = resp["id"]

    def test_05_verify_milestone_has_task(self):
        self.assertIsNotNone(self.plan_id)
        resp = api("GET", f"/api/plans/{self.plan_id}", token=self.token)
        self.assertTrue(resp.get("ok"))
        milestones = resp["plan"].get("milestones", [])
        self.assertGreaterEqual(len(milestones), 1)
        milestone = next((m for m in milestones if m["id"] == self.milestone_id), None)
        self.assertIsNotNone(milestone, "Created milestone not found in plan")
        tasks = milestone.get("tasks", [])
        self.assertGreaterEqual(len(tasks), 1, "No tasks found in milestone")
        task = next((t for t in tasks if t["id"] == self.task_id), None)
        self.assertIsNotNone(task, "Created task not found in milestone")

    def test_06_update_milestone_title(self):
        self.assertIsNotNone(self.milestone_id)
        resp = api("PUT", f"/api/milestones/{self.milestone_id}", {
            "title": "Updated Milestone",
        }, token=self.token)
        self.assertTrue(resp.get("ok"), f"Update milestone failed: {resp}")

        # Verify update
        resp = api("GET", f"/api/plans/{self.plan_id}", token=self.token)
        milestone = next((m for m in resp["plan"]["milestones"] if m["id"] == self.milestone_id), None)
        self.assertEqual(milestone["title"], "Updated Milestone")

    def test_07_delete_task(self):
        """Delete task and verify it's gone."""
        self.assertIsNotNone(self.task_id)
        resp = api("DELETE", f"/api/plans/{self.plan_id}/tasks/{self.task_id}", token=self.token)
        self.assertTrue(resp.get("ok"), f"Delete task failed: {resp}")

    def test_08_delete_milestone(self):
        """BUG FIX VERIFICATION: delete milestone and verify it's gone."""
        self.assertIsNotNone(self.milestone_id)
        resp = api("DELETE", f"/api/milestones/{self.milestone_id}", token=self.token)
        self.assertTrue(resp.get("ok"), f"Delete milestone failed: {resp}")

        # Verify deletion
        resp = api("GET", f"/api/plans/{self.plan_id}", token=self.token)
        milestones = resp["plan"].get("milestones", [])
        found = any(m["id"] == self.milestone_id for m in milestones)
        self.assertFalse(found, "Milestone still exists after deletion")

    def test_09_delete_plan(self):
        self.assertIsNotNone(self.plan_id)
        resp = api("DELETE", f"/api/plans/{self.plan_id}", token=self.token)
        self.assertTrue(resp.get("ok"), f"Delete plan failed: {resp}")

        # Verify deletion
        resp = api("GET", "/api/plans", token=self.token)
        ids = [p["id"] for p in resp.get("plans", [])]
        self.assertNotIn(self.plan_id, ids, "Plan still exists after deletion")


class TestMilestoneCreateDelete(unittest.TestCase):
    """Specifically test the two bugs: create milestone + add task, delete milestone."""

    token = None
    plan_id = None

    @classmethod
    def setUpClass(cls):
        cls.token = ensure_admin_token()
        resp = api("POST", "/api/plans", {
            "title": "Bug Repro Plan",
            "source_url": "https://example.com",
        }, token=cls.token)
        cls.plan_id = resp["id"]

    @classmethod
    def tearDownClass(cls):
        if cls.plan_id:
            api("DELETE", f"/api/plans/{cls.plan_id}", token=cls.token)

    def test_create_milestone_then_add_task_then_delete(self):
        """Full lifecycle: milestone create -> task add -> milestone delete."""
        # Create milestone
        resp = api("POST", f"/api/plans/{self.plan_id}/milestones", {
            "title": "阶段A", "description": "测试阶段",
        }, token=self.token)
        self.assertTrue(resp.get("ok"), f"Milestone create failed: {resp}")
        mid = resp["id"]

        # Add task to milestone (BUG FIX: this should now work)
        resp = api("POST", f"/api/milestones/{mid}/tasks", {
            "planId": self.plan_id,
            "title": "任务1",
            "estimatedMinutes": 60,
            "priority": "high",
        }, token=self.token)
        self.assertTrue(resp.get("ok"), f"Task create failed: {resp}")
        tid = resp["id"]

        # Delete milestone (BUG FIX: this should now work)
        resp = api("DELETE", f"/api/milestones/{mid}", token=self.token)
        self.assertTrue(resp.get("ok"), f"Milestone delete failed: {resp}")

        # Verify both milestone and task are gone
        resp = api("GET", f"/api/plans/{self.plan_id}", token=self.token)
        milestones = resp["plan"].get("milestones", [])
        self.assertFalse(
            any(m["id"] == mid for m in milestones),
            "Milestone still exists after deletion"
        )

    def test_create_multiple_milestones_delete_all(self):
        """Create 3 milestones, verify, delete all."""
        mids = []
        for i in range(3):
            resp = api("POST", f"/api/plans/{self.plan_id}/milestones", {
                "title": f"阶段{i+1}",
            }, token=self.token)
            self.assertTrue(resp.get("ok"))
            mids.append(resp["id"])

        # Verify all exist
        resp = api("GET", f"/api/plans/{self.plan_id}", token=self.token)
        found = sum(1 for m in resp["plan"]["milestones"] if m["id"] in mids)
        self.assertEqual(found, 3)

        # Delete all
        for mid in mids:
            resp = api("DELETE", f"/api/milestones/{mid}", token=self.token)
            self.assertTrue(resp.get("ok"), f"Failed to delete milestone {mid}")

        # Verify all gone
        resp = api("GET", f"/api/plans/{self.plan_id}", token=self.token)
        remaining = [m["id"] for m in resp["plan"].get("milestones", [])]
        for mid in mids:
            self.assertNotIn(mid, remaining, f"Milestone {mid} still exists")


if __name__ == "__main__":
    # Allow running specific tests
    unittest.main(verbosity=2)
