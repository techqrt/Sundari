# Artist service announcement: manual test runbook

Walk through this in order, one step at a time. Admin steps are done in the Django admin (`/admin/`), API steps in Postman
with `artist-announcement.postman_collection.json` (same folder). Each step says what you should see.

## 0. Set up (once)

**Back up the database first.** The dev DB is missing 7 migrations, and the steps below write to it.

```bash
cp db.sqlite3 db.before-manual-test.sqlite3        # restore later with: cp db.before-manual-test.sqlite3 db.sqlite3
venv/bin/python manage.py migrate                  # applies artists 0017, core 0003-0005, help_center 0003,
                                                   # notifications 0006-0007, payments 0003, wallet 0007
```

Start the services, each in its own terminal:

```bash
venv/bin/redis-server                              # broker + rate-limit cache
venv/bin/celery -A sunndari worker -l info         # sends the artist notifications
venv/bin/celery -A sunndari beat -l info           # optional here: the safety net that re-sends a lost announcement
venv/bin/python manage.py runserver
```

*No Redis?* Everything still works except the automatic send. The admin will show a yellow "the queue is unavailable, the
notification will go out shortly" message, the announcement is still saved, and you send it yourself (step 3b).

**Admin login.** A superuser named `admin` exists. If you do not know its password: `venv/bin/python manage.py changepassword admin`.

**Who is who on the dev DB** (user id, role, approval):

| Role | user_id | Notes |
|---|---|---|
| Approved artists | 2, 4, 8, 10, 13 | **These five get the notification.** User 8 (Priynka) has a real FCM device token, so she gets a real push. To avoid it, run `User.objects.filter(pk=8).update(fcm_token=None)` in `manage.py shell` first. |
| Pending artists | 11, 19, 21, 25, 26, 27, 28 | Must NOT be notified. |
| Customers | 1, 3, 9, 12, 20, 23 | Must NOT be notified. User 9 has a device token. |

**Postman tokens.** Edit `WHO` in `mint_tokens.py` if you like (default: artist 2, artist 4, customer 1), then:

```bash
venv/bin/python manage.py shell < docs/manual-testing/mint_tokens.py
```

Paste the printed tokens into the collection variables `artistToken`, `artist2Token`, `customerToken`. (Minting signs that
user out of the real app: one live token per user.)

---

## 1. Admin: create the service, do not announce (Postman folder A)

1. Admin, Core, **Service sub-categories**, **Add**. Category: Makeup. Name: `Diwali Special`. Tick **Is active**.
   Leave **Send notification to artists** unticked. Save.
2. Check the form shows **Send notification to artists** (unticked) and **Notification message** fields, and read-only
   *Activated at*, *Artists announced at*, *Artists notified at*, *Artists announcement message*.
3. Postman folder **A**, in order:
   - A1 customer list: the service is **absent**.
   - A2 artist list: **present**. Put its `subCategoryId` into the `subCategoryId` variable.
   - A3 artist popup: `data: []`.
   - A4 customer popup: **400** "Not allowed to access this resource".
   - A5 artist notifications: nothing new.
4. In admin, list view: the **Artists announced at** column is empty. No notification exists anywhere.

**Pass if:** creating and activating a service sent nothing.

## 2. Admin: things that must be refused or silent

Do these on `Diwali Special` (or a throwaway service); none should send anything:

| Try | Expect |
|---|---|
| Edit the description, Save (box unticked, even with text in the message field) | Saves, **no** notification |
| Untick **Is active**, tick **Send notification to artists**, Save | Form error "Activate the service before notifying artists"; nothing saved |
| Message of 301+ characters with the box ticked | Form error, nothing saved |
| List view, select the service, action **Deactivate selected services**, then **Activate selected services** | Works, **no** notification |
| Create a second service **inactive**, select it, action **Announce selected services to artists** | Red message "<name>: Activate the service before notifying artists"; nothing sent |

Then switch `Diwali Special` back to active.

## 3. Admin: announce it

**3a. From the edit form.** Open `Diwali Special`, tick **Send notification to artists**, message:
`Diwali is coming up! Add a Diwali Special service to your service list.` Save.

- Green message "Diwali Special: artists are being notified." The page now shows **Artists announced at**, and the
  message you sent. The Celery worker log shows the job running.
- Admin, **Log entries** (history of the service): an entry "Announced to artists: ..." with your username.
- Reopen the form: the tick is **not** remembered. Saving again without it sends nothing more.

**3b. Without a worker (no Redis).** Send it by hand:

```bash
venv/bin/python manage.py shell -c "
from sunndari_apps.core.models import ServiceSubCategory as S
from sunndari_apps.core.tasks import notify_artists_service_announced as job
s = S.objects.get(name='Diwali Special')
print(job(s.pk, s.artists_announced_at.isoformat()))"
```

It prints `{'sent': 5, 'skipped': 0, 'failed': 0}`. Run it again: `sent: 0, skipped: 5` (nobody is told twice).

**3c. Bulk action.** Select a different live service, action **Announce selected services to artists**: it goes out with the
standard text "<name> is now available. Add it to your services to start getting bookings."

## 4. API: what artists, customers and the popup now show (Postman folder B)

- B1 artist notifications: one `service_activated` item, title `New service: Diwali Special`, your message,
  `referenceId` = the service id, `bookingId` null. Copy `notificationId`.
- B2 second artist: the same notification. In admin, **Notifications** lists 5 rows (artists 2, 4, 8, 10, 13) and none for
  pending artists or customers.
- B3 customer notifications: nothing about it.
- B4 artist popup: one item with `subCategoryId, name, description, category, message, announcedAt`.
- B5 customer popup: 400.
- B6 customer list: service still **absent**.
- B7 mark the notification read, then B4 again: the popup is **unchanged**.

## 5. The artist adds it (Postman folder C)

C1 add service (201), C2 it is in my services, C3 popup is now empty **for this artist**, C4 customer list **still hides it**
(an offering alone is not enough), C5 create package (201, copy `packageId`), C6 customer list **now shows it**, C7 customer
search finds the artist, C8 the second artist's popup still shows it.

## 6. Visibility follows the packages (folder D) and switching off (folder E)

D1-D4: switch the package off, the customer list hides it; back on, it returns. E1-E5: untick **Is active** in admin
(no tick on the notification box): it disappears for customers and artists, leaves the popup, and adding it is refused
with 400. Admins still see it in the list. Re-activate it: no new notification (compare B1 count).

## 7. Re-announce and edge cases

- Admin, tick the box again with a new message: the artists who have **not** added it get a second notification and the
  popup shows the new `message` and a new `announcedAt`. The artist who added it is still notified, but it does not
  return to their popup.
- Make an artist not approved (admin: set a pending status) and announce: they are not notified.
- Customer search and booking for the service work as before once the package exists.

## 8. Quick checks in the shell (read-only)

```bash
venv/bin/python manage.py shell -c "
from sunndari_apps.notifications.models.notification import Notification as N
from sunndari_apps.core.models import ServiceSubCategory as S
s = S.objects.get(name='Diwali Special')
print(s.artists_announced_at, s.artists_notified_at)          # notified_at set once the job finished
print(N.objects.filter(type='service_activated', reference_id=s.pk).values_list('user_id', flat=True))"
```

## Known limits of this test

Real push delivery depends on the Firebase credentials in your environment (only user 8 has a device token). The Unfold
layout of the new admin fields has only been checked through tests, so tell me if anything looks off on screen.
