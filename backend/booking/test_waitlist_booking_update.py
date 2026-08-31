"""A user on the waitlist must be able to move their booking to a genuinely
available slot, from any panel (Admin / Booking Manager / Client), and the
stale waitlist entry must be removed in the same transaction.

Covers the two root causes fixed:
  1. BookingSerializer.validate_status rejected a client re-submitting the
     booking's *unchanged* status (the edit form always echoes it), so
     clients could not change the time at all.
  2. BookingSerializer had no update()-time waitlist cleanup (create() has
     one), so a reschedule into a waitlisted slot left the entry behind.

Also guards: unavailable slots are still rejected (with a clean 400, not a
stringified dict), and the existing client permission model is unchanged
(no self-confirm / self-complete, cancel still works).
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeamRoleAssignment, User
from clients.models import Client

from .models import Booking, Service, Waitlist

FUTURE = date.today() + timedelta(days=7)


class WaitlistedBookingRescheduleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.service = Service.objects.create(name="Consult", hourly_rate=Decimal("100.00"))

        self.user = User.objects.create_user(
            username="c1", email="c1@example.com", password="test-pass-12345", full_name="C One"
        )
        self.client_rec = Client.objects.create(full_name="C One", email="c1@example.com")
        self.other = Client.objects.create(full_name="C Two", email="c2@example.com")

        # Acting client's current booking: 10:00-11:00
        self.booking = Booking.objects.create(
            client=self.client_rec, service=self.service, service_name="Consult",
            booking_date=FUTURE, start_time=time(10, 0), end_time=time(11, 0),
            price=Decimal("100.00"), rate_snapshot=Decimal("100.00"),
            status=Booking.BookingStatus.PENDING, created_by=self.user,
        )
        # Another client holds the desired slot 14:00-15:00
        self.other_booking = Booking.objects.create(
            client=self.other, service=self.service, service_name="Consult",
            booking_date=FUTURE, start_time=time(14, 0), end_time=time(15, 0),
            price=Decimal("100.00"), rate_snapshot=Decimal("100.00"),
            status=Booking.BookingStatus.PENDING, created_by=self.user,
        )
        # Acting client waitlists 14:00-15:00
        self.wl = Waitlist.objects.create(
            client=self.client_rec, booking_date=FUTURE,
            start_time=time(14, 0), end_time=time(15, 0),
        )

    # -- helpers -----------------------------------------------------------
    def _free_desired_slot(self):
        self.other_booking.status = Booking.BookingStatus.CANCELLED
        self.other_booking.save(update_fields=["status"])

    def _api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def _staff(self, role):
        u = User.objects.create_user(
            username=role.replace(" ", "").lower(),
            email=f"{role.replace(' ', '').lower()}@example.com",
            password="test-pass-12345", full_name=role,
        )
        TeamRoleAssignment.objects.create(role_name=role, assigned_user=u)
        return u

    def _reschedule_payload(self, start="14:00:00", end="15:00:00", status="PENDING"):
        return {
            "booking_date": str(FUTURE),
            "start_time": start,
            "end_time": end,
            "status": status,
            "notes": "",
        }

    def _assert_moved_and_waitlist_cleared(self, resp):
        self.assertEqual(resp.status_code, 200, resp.data)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.start_time, time(14, 0))
        self.assertEqual(self.booking.end_time, time(15, 0))
        self.assertFalse(
            Waitlist.objects.filter(
                client=self.client_rec, booking_date=FUTURE,
                start_time=time(14, 0), end_time=time(15, 0),
            ).exists(),
            "the stale waitlist entry should have been removed",
        )

    # -- the three panels ------------------------------------------------
    def test_client_can_move_booking_into_its_waitlisted_slot(self):
        self._free_desired_slot()
        resp = self._api(self.user).patch(
            f"/api/bookings/{self.booking.id}/", self._reschedule_payload(), format="json"
        )
        self._assert_moved_and_waitlist_cleared(resp)

    def test_booking_manager_can_move_a_clients_booking_into_its_waitlisted_slot(self):
        self._free_desired_slot()
        resp = self._api(self._staff("Booking Manager")).patch(
            f"/api/bookings/{self.booking.id}/", self._reschedule_payload(), format="json"
        )
        self._assert_moved_and_waitlist_cleared(resp)

    def test_admin_can_move_a_clients_booking_into_its_waitlisted_slot(self):
        self._free_desired_slot()
        resp = self._api(self._staff("Admin")).patch(
            f"/api/bookings/{self.booking.id}/", self._reschedule_payload(), format="json"
        )
        self._assert_moved_and_waitlist_cleared(resp)

    def test_put_full_update_also_clears_the_waitlist_entry(self):
        self._free_desired_slot()
        admin = self._staff("Admin")
        resp = self._api(admin).put(
            f"/api/bookings/{self.booking.id}/",
            {
                "client": self.client_rec.id,
                "service": self.service.id,
                "booking_date": str(FUTURE),
                "start_time": "14:00:00",
                "end_time": "15:00:00",
                "status": "PENDING",
                "notes": "",
            },
            format="json",
        )
        self._assert_moved_and_waitlist_cleared(resp)

    # -- requirement 5: unavailable slot still rejected, cleanly ---------
    def test_moving_into_a_still_booked_slot_is_rejected(self):
        # other_booking is still active at 14:00-15:00
        resp = self._api(self._staff("Admin")).patch(
            f"/api/bookings/{self.booking.id}/", self._reschedule_payload(), format="json"
        )
        self.assertEqual(resp.status_code, 400)
        # Clean, field-keyed body — not {"error": "{'non_field_errors': [ErrorDetail(...)]}"}
        self.assertIn("non_field_errors", resp.data)
        self.assertNotIn("error", resp.data)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.start_time, time(10, 0), "booking must not have moved")
        self.assertTrue(Waitlist.objects.filter(client=self.client_rec).exists())

    def test_client_moving_into_a_still_booked_slot_is_rejected_cleanly(self):
        resp = self._api(self.user).patch(
            f"/api/bookings/{self.booking.id}/", self._reschedule_payload(), format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("error", resp.data)

    # -- requirement 4: existing behaviour preserved -------------------
    def test_client_notes_only_edit_now_works(self):
        resp = self._api(self.user).patch(
            f"/api/bookings/{self.booking.id}/",
            {"booking_date": str(FUTURE), "start_time": "10:00:00", "end_time": "11:00:00",
             "status": "PENDING", "notes": "please call ahead"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.notes, "please call ahead")

    def test_client_still_cannot_self_confirm(self):
        resp = self._api(self.user).patch(
            f"/api/bookings/{self.booking.id}/", self._reschedule_payload(status="CONFIRMED"),
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.BookingStatus.PENDING)

    def test_client_can_still_cancel_their_own_booking(self):
        resp = self._api(self.user).patch(
            f"/api/bookings/{self.booking.id}/",
            {"status": "CANCELLED"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.BookingStatus.CANCELLED)

    def test_staff_reschedule_without_a_waitlist_still_works(self):
        Waitlist.objects.all().delete()
        self._free_desired_slot()
        resp = self._api(self._staff("Admin")).patch(
            f"/api/bookings/{self.booking.id}/", self._reschedule_payload(), format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.start_time, time(14, 0))

    def test_other_clients_waitlist_entries_are_untouched(self):
        # A different client waiting on the same slot must NOT be removed —
        # only the rescheduled booking's own client's entry is cleared.
        Waitlist.objects.create(
            client=self.other, booking_date=FUTURE,
            start_time=time(14, 0), end_time=time(15, 0),
        )
        self._free_desired_slot()
        resp = self._api(self._staff("Admin")).patch(
            f"/api/bookings/{self.booking.id}/", self._reschedule_payload(), format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(
            Waitlist.objects.filter(
                client=self.other, start_time=time(14, 0), end_time=time(15, 0)
            ).exists()
        )
        self.assertFalse(
            Waitlist.objects.filter(
                client=self.client_rec, start_time=time(14, 0), end_time=time(15, 0)
            ).exists()
        )
