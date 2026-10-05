"""Hand-written content for the frontend guide. Edit here, then re-run build_frontend_guide.py.

In narrative text, write [[METHOD /path/]] to get a checked link to that endpoint's reference card
(the build fails if the endpoint does not exist)."""
import re

BASE_COMMIT = '7d5ad358ec736494ac9c36f9fdc4273eb1c40064'      # "previous release": NEW = not routed in this commit

# ───────────────────────── who can call what ─────────────────────────
ROLE_PREFIXES = [
    ('/auth/', 'Public (no login)'), ('/core/pages/', 'Public (no login)'), ('/public/', 'Public (no login)'),
    ('/admin-panel/', 'Admin'), ('/help_center/admin/', 'Admin'), ('/help_center/artist/', 'Artist'),
    ('/help_center/tickets/', 'Customer or artist'), ('/help_center/', 'Customer'),
    ('/artists/', 'Artist'), ('/customers/', 'Customer'),
]
_ANY_VIA_ID = 'Artist (own data) · any logged-in user for an approved artist via <code>artist_id</code>'
ROLE_OVERRIDES = {
    '/artists/profile/get/': 'Any logged-in user (no <code>artist_id</code> = your own; with it = that artist)',
    '/artists/portfolio/get_all/': _ANY_VIA_ID, '/artists/packages/get_all/': _ANY_VIA_ID, '/artists/addons/get_all/': _ANY_VIA_ID,
    '/artists/service_areas/get_all/': _ANY_VIA_ID, '/artists/profile/specialities/get_all/': _ANY_VIA_ID,
    '/artists/services/get_all/': _ANY_VIA_ID, '/artists/locations/get_all/': _ANY_VIA_ID,
    '/artists/documents/file/': 'The owning artist, or an admin',
    '/help_center/admin/chat/': 'Admin (browser page)',
}

TAG_GROUPS = [
    ('Authentication', ['Authentication - Phone OTP', 'Authentication - Email OTP', 'Authentication - Password', 'Authentication - Google', 'Authentication']),
    ('Users', ['Users - Profile', 'Users - Address']),
    ('Artist · profile & onboarding', ['Artists - Profile', 'Artists - Onboarding', 'Artists - Services', 'Artists - Locations', 'Artists - Availability']),
    ('Artist · catalogue', ['Artists - Portfolio', 'Artists - Packages', 'Artists - Add-ons', 'Artists - Service areas', 'Artists - Brands']),
    ('Artist · bookings & business', ['Artists - Bookings', 'Artists - Reschedule', 'Artists - Reviews', 'Artists - Customer reviews', 'Artists - Clients', 'Artists - Insights']),
    ('Customer', ['Customers - Search', 'Customers - Artists', 'Customers - Booking', 'Customers - Reschedule', 'Customers - Reviews']),
    ('Payments & wallet', ['Customers - Payment', 'Customers - Wallet']),
    ('Support, chat & notifications', ['Chat', 'Notifications', 'Help Center', 'Help Center Artist', 'Help center - Tickets']),
    ('Admin', ['Admin - Artist Review', 'Admin - Brands', 'Help Center Admin', 'Help center - Admin tickets']),
    ('Core data & public', ['Core - Service Category', 'Core - Service Sub-Category', 'Core - Location Type', 'Core - Statuses', 'Core - Brands', 'Core - Pages', 'Public']),
]

# ───────────────────────── file upload fields (not visible in the JSON schema) ─────────────────────────
FILE_FIELDS = {
    '/artists/documents/create/': [
        ('file', 'JPEG / PNG / WEBP / PDF', 'yes', 'Front of the document, max 5 MB. Content is inspected — a renamed file is rejected.'),
        ('back_file', 'JPEG / PNG / WEBP / PDF', 'conditional', 'Required for <code>aadhaar</code>, <code>voter_id</code>, <code>driving_licence</code>; optional for <code>passport</code>; only valid for <code>id_proof</code>.')],
    '/artists/portfolio/create/': [
        ('file', 'image or video', 'yes', 'Image: JPEG/PNG/WEBP, max 5 MB. Video (<code>media_type=video</code>): mp4 / mov / webm, max 50 MB. Work samples must be images.')],
    '/artists/profile/photo/upload/': [
        ('profile_photo', 'JPEG / PNG / WEBP', 'one of the two', 'Max 5 MB. Replaces the current profile photo.'),
        ('cover_photo', 'JPEG / PNG / WEBP', 'one of the two', 'Max 5 MB. Replaces the current cover photo.')],
    '/artists/packages/photo/upload/': [('photo', 'JPEG / PNG / WEBP', 'yes', 'Max 5 MB. Replaces the current package photo.')],
    '/help_center/tickets/create/': [('attachments', 'JPEG / PNG / WEBP / PDF (repeatable)', 'no', 'Up to 5 files — repeat the field name once per file. Max 5 MB each.')],
}

# ───────────────────────── response examples for endpoints whose data is not described by the schema ─────────────────────────
_TICKET = {'ticketId': 15, 'issueType': 'payment', 'subject': 'Charged twice', 'description': 'I was charged two times', 'bookingId': 41, 'status': 'open', 'resolutionNote': None,
           'attachments': [{'attachmentId': 4, 'url': '/help_center/tickets/attachment/?attachment_id=4'}], 'createdAt': '2026-10-05T10:00:00+00:00', 'updatedAt': '2026-10-05T10:00:00+00:00'}
_PAGE = lambda items: {'data': items, 'presentPage': 1, 'totalPage': 1}
RETURNS = {
    '/artists/portfolio/create/': {'portfolio_id': 12}, '/artists/packages/create/': {'package_id': 7}, '/artists/addons/create/': {'addon_id': 3},
    '/artists/service_areas/add/': {'area_id': 4}, '/artists/documents/create/': {'document_id': 9},
    '/artists/bookings/reschedule/request/': {'reschedule_id': 5, 'expires_at': '2026-10-06T10:00:00+00:00'},
    '/help_center/tickets/create/': {'ticket_id': 15}, '/artists/brands/request/': {'request_id': 2}, '/admin-panel/brands/create/': {'brand_id': 6},
    '/artists/customer_reviews/create/': {'customer_review_id': 3}, '/customers/reviews/create/': {'review_id': 8},
    '/customers/bookings/create/': {'booking_id': 41, 'total_amount': '2500.00', 'travel_fee': '0.00'},
    '/customers/payments/initiate/': {'payment_id': 18, 'gateway_order_id': 'order_Nxyz123', 'razorpay_key_id': 'rzp_live_xxxx', 'amount': 250000, 'currency': 'INR'},
    '/artists/profile/accepting_bookings/': {'isAcceptingBookings': False},
    '/artists/profile/share_link/': {'slug': 'glam-studio-a1b2c3', 'url': 'https://api.example.com/public/artists/get/?slug=glam-studio-a1b2c3'},
    '/artists/profile/specialities/get_all/': [{'subCategoryId': 3, 'name': 'Bridal Makeup'}],
    '/artists/insights/summary/': {'fromDate': None, 'toDate': None, 'totalBookings': 12, 'bookingsByStatus': {'completed': 8, 'cancelled': 2, 'pending': 2}, 'completedBookings': 8,
                                   'cancelledBookings': 2, 'repeatClients': 3, 'topServices': [{'subCategoryId': 3, 'name': 'Bridal Makeup', 'bookings': 5}], 'profileViews': 142},
    '/artists/clients/get_all/': _PAGE([{'customerId': 21, 'name': 'Riya', 'bookingsCount': 3, 'completedBookings': 2, 'lastBookingDate': '2026-10-12', 'note': 'Allergic to latex', 'noteUpdatedAt': '2026-10-05T09:00:00+00:00'}]),
    '/artists/customer_reviews/get_all/': _PAGE([{'customerReviewId': 3, 'bookingId': 41, 'customerId': 21, 'customerName': 'Riya', 'rating': 5, 'comment': 'Punctual and polite', 'createdAt': '2026-10-12T12:00:00+00:00'}]),
    '/artists/brands/requests/get_all/': _PAGE([{'requestId': 2, 'name': 'Charlotte Tilbury', 'status': 'pending', 'adminNote': None, 'decidedAt': None, 'createdAt': '2026-10-05T10:00:00+00:00'}]),
    '/admin-panel/brands/requests/get_all/': _PAGE([{'requestId': 2, 'artistId': 7, 'artistName': 'Glam Studio', 'name': 'Charlotte Tilbury', 'status': 'pending', 'adminNote': None, 'decidedAt': None, 'createdAt': '2026-10-05T10:00:00+00:00'}]),
    '/core/brands/get_all/': _PAGE([{'brandId': 1, 'name': 'MAC'}]),
    '/core/pages/get/': {'termsUrl': 'https://sunndari.in/terms', 'privacyUrl': 'https://sunndari.in/privacy', 'contactEmail': 'help@sunndari.in', 'contactPhone': None, 'agreementVersion': '1.0'},
    '/help_center/tickets/get/': _TICKET, '/help_center/tickets/get_all/': _PAGE([_TICKET]),
    '/help_center/admin/tickets/get/': {**_TICKET, 'userId': 21, 'userName': 'Riya', 'userRole': 'customer'},
    '/help_center/admin/tickets/get_all/': _PAGE([{**_TICKET, 'userId': 21, 'userName': 'Riya', 'userRole': 'customer'}]),
    '/artists/documents/file/': None,
    '/public/artists/get/': {'displayName': 'Glam Studio', 'profileType': 'studio', 'bio': 'Bridal specialist', 'city': 'Lucknow', 'yearsExperience': 6, 'instagramUrl': 'https://instagram.com/glam',
                             'avgRating': '4.80', 'totalReviews': 25, 'isAcceptingBookings': True, 'profilePhotoUrl': 'https://api.example.com/media/artist_photos/artist_7/a.png', 'coverPhotoUrl': None,
                             'specialities': ['Bridal Makeup'], 'serviceAreas': ['Lucknow'],
                             'packages': [{'packageId': 7, 'subCategoryId': 3, 'name': 'Bridal', 'price': '3000.00', 'durationMinutes': 90, 'description': None, 'makeupType': 'HD', 'productDetails': None,
                                           'photoUrl': None, 'brands': ['MAC'], 'category': {'categoryId': 1, 'name': 'Makeup'}, 'inclusions': []}],
                             'portfolio': [{'fileUrl': 'https://api.example.com/media/portfolios/artist_7/x.png', 'mediaType': 'image', 'caption': 'Bridal look'}]},
    '/admin-panel/artists/review/get/': {'artistId': 7, 'userId': 30, 'fullName': 'Asha Verma', 'displayName': 'Glam Studio', 'dateOfBirth': '1992-03-04', 'instagramUrl': 'https://instagram.com/glam',
                                         'profilePhotoUrl': '/media/artist_photos/artist_7/a.png', 'coverPhotoUrl': None, 'profileType': 'studio', 'bio': 'Bridal specialist', 'yearsExperience': 6,
                                         'city': 'Lucknow', 'specialities': [{'subCategoryId': 3, 'name': 'Bridal Makeup'}], 'workSamples': [{'portfolioId': 40, 'fileUrl': '/media/portfolios/artist_7/w.png', 'caption': None}],
                                         'approvalStatus': 'pending', 'submittedForReviewAt': '2026-10-05T10:00:00+00:00', 'rejectionReason': None},
}
RETURNS = {k: v for k, v in RETURNS.items() if v is not None}
MESSAGES = {
    '/customers/bookings/create/': 'Slot locked. Complete payment within 15 minutes.', '/customers/payments/initiate/': 'Payment initiated. Complete payment using the returned order reference.',
    '/artists/documents/create/': 'Document uploaded successfully',
}

# ───────────────────────── extra notes / field notes ─────────────────────────
ENDPOINT_NOTES = {
    '/artists/documents/file/': 'Returns the <b>file bytes</b>, not JSON. It needs the Bearer header, so a plain <code>&lt;img src&gt;</code> will not work — fetch it with your HTTP client and show a blob/object URL. Query: <code>document_id</code>, optional <code>side=front|back</code> (default front).',
    '/help_center/tickets/attachment/': 'Returns the <b>file bytes</b> (needs the Bearer header — fetch and show as a blob).',
    '/customers/payments/initiate/': 'Send the <code>booking_id</code> only (and <code>amount</code> for an advance/partial payment). <b>Never send a price</b> — the server computes it. Status <b>201</b> = new order; status <b>200</b> = an identical open order already existed and is returned again (same <code>gateway_order_id</code>) — treat both as success and open the Razorpay checkout with the returned order.',
    '/customers/payments/verify/': 'Call this right after Razorpay Checkout succeeds, with the three values Razorpay returns. It is idempotent: calling it again for a verified payment returns success.',
    '/users/profile/get/': 'Pass <code>user_id</code>. You get your <b>own</b> full profile; for anyone else only <code>userId</code>, <code>name</code>, <code>role</code> (admins also see contact details). The access token is never returned.',
    '/artists/profile/get/': 'Without <code>artist_id</code> you get <b>your own</b> full profile. With <code>artist_id</code> of another artist you get only the public subset, and only if that artist is approved (otherwise a 400 "No matching record found"). Private to the owner: <code>dateOfBirth</code>, <code>commissionRate</code>, review/approval fields, <code>baseAddressId</code>, <code>termsAcceptedAt</code>, <code>agreementVersion</code>, <code>publicSlug</code>, <code>profileViewCount</code>, buffer minutes.',
    '/customers/artists/availability/': 'To grey out unavailable times: a new appointment from <i>start</i> to <i>end</i> is free only if <code>[start − bufferBeforeMinutes, end + bufferAfterMinutes]</code> does not overlap any range in <code>blockedRanges</code> (buffers apply to <b>Home Visit</b> bookings only; use 0 for studio visits) and lies inside <code>workingWindow</code> on a day that is not <code>isBlocked</code>. <code>bookedRanges</code> are the raw appointments.',
    '/artists/bookings/reschedule/request/': 'The booking keeps its length (package + add-ons); only the start moves. The customer has 24 hours (or until the original start, whichever is sooner) to answer.',
    '/users/contact/change/request/': 'Send <b>exactly one</b> of <code>email</code> / <code>phone_number</code>. The code is sent to the <b>new</b> contact. One request per minute.',
    '/artists/profile/share_link/': 'Creates the artist\'s share handle on first call; the same link is returned afterwards. Open it in a browser or share it — see <a href="#get-public-artists-get">the public page</a>.',
    '/public/artists/get/': 'No login needed. Works only for approved artists. Each call counts as a profile view.',
    '/customers/bookings/start_pin/': 'The customer reads the PIN and tells it to the artist, who enters it with the artist start-PIN endpoint.',
    '/customers/bookings/completion_pin/': 'Same idea as the start PIN, issued when the service starts.',
    '/artists/bookings/arrived/': 'The artist enters the <b>booking OTP</b> (shown to the artist in their notification when the booking is created). The OTP is single-use.',
    '/artists/documents/create/': 'For <code>document_type=id_proof</code> you must also send <code>id_type</code> and <code>document_number</code>; a new ID proof <b>replaces</b> the previous one and goes back to <code>pending</code> verification.',
    '/artists/onboarding/status/': 'Drive the onboarding checklist UI from <code>steps</code>. <code>status</code> is one of <code>not_started</code>, <code>in_progress</code>, <code>submitted</code>, <code>approved</code>, <code>rejected</code>, <code>suspended</code>.',
    '/auth/reset-password/': 'Succeeds with 200 and revokes existing sessions: send the user to the login screen afterwards.',
    '/auth/forgot-password/': 'Always answers 200 (even for unknown accounts) so account existence is not revealed.',
}
FIELD_NOTES = {
    '/customers/bookings/get/': [('travelFee, addOns', 'always present for customers. <code>platformFee</code>, <code>netAmount</code> and the buffer fields are <b>never</b> sent to customers.')],
    '/customers/bookings/get_all/': [('travelFee, addOns', 'always present for customers. <code>platformFee</code> / <code>netAmount</code> are never sent to customers.')],
    '/artists/bookings/get/': [('platformFee, netAmount', 'artist-only figures, snapshotted when the booking was made (<code>null</code> on bookings created before this release). <code>travelMinutesBefore</code> / <code>returnBufferMinutes</code> likewise.')],
    '/artists/bookings/get_all/': [('platformFee, netAmount', 'artist-only; <code>null</code> on older bookings.')],
}

# ───────────────────────── what changed on existing endpoints ─────────────────────────
B, CH = 'breaking', 'changed'
CHANGED = {
    '/auth/register/': (CH, 'Only <code>customer</code> and <code>artist</code> are accepted for <code>role</code> (<code>admin</code> → 400). Password must be ≥ 8 chars and not purely numeric or a common password (e.g. <code>12345678</code>, <code>password</code>) → 400 with a field error.'),
    '/auth/phone-otp/request/': (CH, '<code>role</code> may only be <code>customer</code> or <code>artist</code>.'),
    '/auth/email-otp/request/': (CH, '<code>role</code> may only be <code>customer</code> or <code>artist</code>.'),
    '/auth/google/': (CH, '<code>role</code> may only be <code>customer</code> or <code>artist</code>.'),
    '/auth/login/': (CH, 'A deactivated account now gets <b>HTTP 403</b> ("This account is deactivated") instead of a token.'),
    '/auth/phone-otp/verify/': (CH, 'Deactivated account → HTTP 403 instead of a token.'),
    '/auth/email-otp/verify/': (CH, 'Deactivated account → HTTP 403 instead of a token.'),
    '/auth/token/refresh/': (CH, 'Deactivated account → HTTP 403.'),
    '/users/profile/get/': (B, 'The response no longer contains <code>access_token</code> (it never should have). For a user other than yourself you now get only <code>userId</code>, <code>name</code>, <code>role</code>; <code>email</code>, <code>phoneNumber</code>, <code>isActive</code>, <code>createdAt</code> are present only on your own profile (or for admins); <code>fcmToken</code> is yours alone. Make those fields optional in your models.'),
    '/users/profile/update/': (B, '<b>Email and phone can no longer be changed here</b> — sending a value different from the current one returns 400. Send only <code>name</code> / <code>fcm_token</code>. Use [[POST /users/contact/change/request/]] + [[POST /users/contact/change/verify/]] (OTP-verified) to change a contact.'),
    '/artists/profile/get/': (CH, 'New fields: <code>displayName</code>, <code>dateOfBirth</code> (own only), <code>instagramUrl</code>, <code>profileType</code>, <code>specialities</code> (array of sub-category ids), <code>profilePhotoUrl</code>, <code>coverPhotoUrl</code> (absolute URLs or <code>null</code>), <code>isAcceptingBookings</code>, and (own only) <code>publicSlug</code>, <code>profileViewCount</code>, <code>agreementVersion</code>, <code>travelTimeBeforeMinutes</code>, <code>returnBufferMinutes</code>. Viewing <i>another</i> artist returns only the public subset, and only for approved artists.'),
    '/artists/profile/update/': (CH, 'New optional fields: <code>display_name</code>, <code>date_of_birth</code> (YYYY-MM-DD, age ≥ 18), <code>instagram_url</code> (<code>https://instagram.com/&lt;handle&gt;</code> only), <code>profile_type</code> (<code>freelance</code>|<code>studio</code>), <code>travel_time_before_minutes</code>, <code>return_buffer_minutes</code> (0–240). Commission, approval, rating etc. are ignored if sent.'),
    '/artists/profile/agreement/accept/': (CH, 'Now records the accepted <b>version</b> as well as the date (<code>agreementVersion</code> on the profile).'),
    '/artists/services/add/': (CH, 'Adding a service no longer sends an approved artist back to <code>pending</code>.'),
    '/artists/services/remove/': (CH, 'No longer demotes an approved artist. Removing a service also removes it from the artist\'s specialities.'),
    '/artists/portfolio/create/': (CH, 'New optional <code>is_work_sample</code> (max 5 per artist, images only; kept out of the public portfolio, shown to admins during review). Files are content-checked (JPEG/PNG/WEBP up to 5 MB; video mp4/mov/webm up to 50 MB). A non-existent <code>sub_category_id</code> is rejected.'),
    '/artists/portfolio/get_all/': (CH, 'Items are returned in <code>sortOrder</code> (see [[PUT /artists/portfolio/reorder/]]); each item has new <code>isWorkSample</code> and <code>sortOrder</code>. For another artist (<code>artist_id</code>) you only get active items of <b>approved</b> artists, and never their work samples.'),
    '/artists/portfolio/delete/': (CH, 'Also deletes the stored media file.'),
    '/artists/packages/create/': (CH, 'New optional fields: <code>makeup_type</code>, <code>brands</code> (free-text list, max 10), <code>product_details</code>. Add the photo with [[PUT /artists/packages/photo/upload/]].'),
    '/artists/packages/update/': (CH, 'Same new optional fields as create; <code>brands: []</code> clears the list. Existing bookings keep their own snapshot.'),
    '/artists/packages/get/': (CH, 'Response adds <code>makeupType</code>, <code>brands</code>, <code>productDetails</code>, <code>photoUrl</code> (absolute or <code>null</code>) and a derived <code>category</code> <code>{categoryId, name}</code>.'),
    '/artists/packages/get_all/': (CH, 'Same new fields per package. For another artist you only get active packages of approved artists.'),
    '/artists/payout_account/set/': (CH, '<code>bank_account_number</code> must be 6–30 <b>digits</b> only. Changing the account resets its verification to <code>pending</code> and notifies the artist.'),
    '/artists/documents/create/': (B, 'Now needs <code>id_type</code> (<code>aadhaar</code>|<code>voter_id</code>|<code>passport</code>|<code>driving_licence</code>) and <code>document_number</code> for an ID proof, plus a <code>back_file</code> for aadhaar / voter_id / driving_licence. Numbers are validated per type. Files are content-checked. A new ID proof replaces the old one.'),
    '/artists/documents/get/': (B, '<code>fileUrl</code> is now an API <b>route</b> (<code>/artists/documents/file/?document_id=…</code>), not a media path — prepend your base URL and fetch it with the Bearer header. New fields <code>idType</code>, <code>backFileUrl</code>; <code>documentNumber</code> is <b>masked</b> (only the last 4 characters).'),
    '/artists/documents/get_all/': (B, 'Same as the single get: <code>fileUrl</code>/<code>backFileUrl</code> are authenticated routes, <code>documentNumber</code> is masked, new <code>idType</code>.'),
    '/artists/documents/delete/': (CH, 'Also deletes the stored files.'),
    '/artists/onboarding/status/': (CH, '<code>steps</code> has two new booleans, <code>registrationFields</code> and <code>workSamples</code>; new <code>latestFeedback</code> (<code>null</code> or the last admin decision).'),
    '/artists/onboarding/submit/': (CH, 'Stricter: also requires display name, date of birth, profile type and at least one work sample. Approval additionally needs the ID proof to be verified by an admin.'),
    '/customers/artists/search/': (CH, 'Artists who switched bookings off no longer appear.'),
    '/customers/artists/get/': (CH, 'Adds <code>addOns</code> (active, each with <code>packageIds</code>) and <code>serviceAreas</code> (active); <code>profile</code> gains <code>displayName</code>, <code>instagramUrl</code>, <code>profileType</code>, <code>isAcceptingBookings</code>; packages gain the new package fields; portfolio is in the artist\'s chosen order and excludes work samples. Each successful call counts as a profile view.'),
    '/customers/artists/availability/': (CH, 'Adds <code>blockedRanges</code>, <code>bufferBeforeMinutes</code>, <code>bufferAfterMinutes</code> — use these (not just <code>bookedRanges</code>) to decide which times to offer.'),
    '/customers/bookings/create/': (CH, 'New optional <code>addon_ids</code>. The <b>total is computed on the server</b> (package + add-ons + travel fee); any price you send is ignored. Response now includes <code>total_amount</code> and <code>travel_fee</code>. New refusals: your own services, an artist who switched bookings off, an add-on that is inactive/not linked to the package, a Home Visit address outside the artist\'s service areas (or no address when the artist has areas), a slot that clashes with another booking\'s travel/return buffers.'),
    '/customers/bookings/get/': (CH, 'Adds <code>travelFee</code> and <code>addOns</code> (each <code>{addOnId, name, price, durationMinutes}</code>). <code>totalAmount</code> already includes both.'),
    '/customers/bookings/get_all/': (CH, 'Each booking adds <code>travelFee</code> and <code>addOns</code>.'),
    '/customers/bookings/cancel/': (CH, 'Refused (400) once the booking is <code>in_progress</code> or the artist has arrived. Cancelling a paid booking now asks the payment gateway for a refund (see Payments flow).'),
    '/artists/bookings/get/': (CH, 'Adds artist-only <code>platformFee</code>, <code>netAmount</code>, <code>travelMinutesBefore</code>, <code>returnBufferMinutes</code> plus <code>travelFee</code> and <code>addOns</code>.'),
    '/artists/bookings/get_all/': (CH, 'Same additions per booking.'),
    '/artists/bookings/update_status/': (CH, 'Cancelling/declining a paid booking now triggers a real gateway refund (the customer gets a "refund initiated" or "refund being processed" notification).'),
    '/customers/payments/initiate/': (CH, 'Idempotent: an identical open order is returned again (HTTP <b>200</b>, same order id). A second order that would exceed what is still owed is refused (400 "A payment for this booking is already in progress…"). Open orders older than 30 minutes no longer block.'),
    '/customers/payments/verify/': (CH, 'A capture that would push the booking above its total is refused (400 "…exceed the booking total… will be refunded") and the payment is marked failed.'),
    '/customers/reviews/get/': (CH, 'Reviews now include <code>reply</code> and <code>repliedAt</code> (the artist\'s answer, or <code>null</code>).'),
    '/customers/reviews/get_all/': (CH, 'Each review includes <code>reply</code> and <code>repliedAt</code>.'),
    '/admin-panel/artists/approve/': (CH, 'Optional <code>message</code> (kept in the artist\'s feedback history). Requires the artist\'s ID proof to be <b>verified</b> first, refuses suspended artists, is idempotent, and notifies the artist.'),
    '/admin-panel/artists/reject/': (CH, 'The reason is added to the artist\'s feedback history and sent as a notification; refuses suspended artists.'),
}


# ───────────────────────── helpers used by the builder ─────────────────────────
_REF = re.compile(r'\[\[(GET|POST|PUT|DELETE|PATCH) (/[^\]\s]*)\]\]')


def link_endpoints(text, anchors):
    def repl(match):
        method, path = match.group(1), match.group(2)
        return f'<a class="eplink" href="#{anchors[(method, path)]}"><b>{method}</b> {path}</a>'
    return _REF.sub(repl, text)


def _all_narrative():
    parts = [OVERVIEW, START_HERE, CHANGES_STATIC, FLOWS] + [v[1] for v in CHANGED.values()]
    return '\n'.join(parts)


def referenced_endpoints():
    return sorted(set((m, p) for m, p in _REF.findall(_all_narrative())))


# ═════════════════════════════ NARRATIVE ═════════════════════════════
OVERVIEW = """
<div class="legend">
  <span class="badge badge-new">new</span> endpoint did not exist in the previous release &nbsp;·&nbsp;
  <span class="badge badge-chg">changed</span> existing endpoint behaves or returns something different &nbsp;·&nbsp;
  <span class="badge badge-brk">breaking</span> your current integration breaks unless you update it &nbsp;·&nbsp;
  <span class="badge badge-mp">multipart</span> sends files (<code>multipart/form-data</code>)
</div>
<h3>Not available yet (do not build against these)</h3>
<ul>
  <li><b>Earnings, payouts, payout history</b> — deferred. Bank details are stored (encrypted) but nothing pays out.</li>
  <li><b>Per-kilometre travel charges</b> — only <code>free</code> and <code>per_visit</code> work; <code>per_km</code> is rejected.</li>
  <li><b>Marketing Studio content generation</b> and <b>service-styles list</b> — not built yet (waiting on a spec).</li>
  <li><b>Logout endpoint</b> — there is none; a session ends when the user logs in elsewhere, the token expires (access 7 days, refresh 30 days), or the client discards it.</li>
  <li>Account deletion and artist suspension through the API — not exposed.</li>
</ul>
"""

START_HERE = """
<p>In priority order — items 1–4 can break existing screens, so do them first.</p>
<ol class="check">
  <li><b>Everyone will be logged out once.</b> After the security release all stored tokens are revoked. On <b>any 401</b> clear the session and show the login screen; never loop on refresh.</li>
  <li><b>Stop using <code>GET /users/profile/get/</code> for other people.</b> It now returns only <code>userId, name, role</code> for anyone but you, and never returns a token. Make <code>email</code>, <code>phoneNumber</code>, <code>isActive</code>, <code>createdAt</code>, <code>fcmToken</code> optional in your model. (<a href="#get-users-profile-get">details</a>)</li>
  <li><b>Remove email / phone from the “edit profile” save.</b> [[PUT /users/profile/update/]] now rejects a changed email/phone. Use the new OTP flow ([[POST /users/contact/change/request/]] → [[POST /users/contact/change/verify/]]).</li>
  <li><b>KYC screen:</b> new required fields (<code>id_type</code>, <code>document_number</code>, back image) and <code>fileUrl</code> is now an authenticated route you must fetch with the token (see <a href="#flow-kyc">KYC flow</a>).</li>
  <li><b>Artist registration / onboarding:</b> add the new profile fields, specialities, photos, work samples, the bank form, agreement, status screen with admin feedback, resubmit (<a href="#flow-onboarding">flow</a>).</li>
  <li><b>Booking creation:</b> never send a price. Add add-ons, show travel fee, use <code>blockedRanges</code> + buffers for the time picker, handle the new refusals (<a href="#flow-booking">flow</a>).</li>
  <li><b>Payments:</b> accept HTTP 200 <i>or</i> 201 from initiate; handle “payment already in progress”; refund wording (<a href="#flow-payment">flow</a>).</li>
  <li><b>New artist tools:</b> add-ons, service areas, brands, reschedule, reviews &amp; replies, clients with notes, insights, accepting-bookings switch, share link (<a href="#flow-artist-tools">flow</a>).</li>
  <li><b>New shared features:</b> support tickets with attachments, Terms/Privacy/Contact info, forgot/reset password.</li>
  <li><b>Authorization failures are still HTTP 400</b> (not 403) with <code>message</code> “Not allowed to access this resource” or “No matching record found” — keep reading the message, not just the code.</li>
</ol>
"""

CHANGES_STATIC = """
<h3 id="breaking">Breaking changes (update these first)</h3>
<div class="tablewrap"><table><thead><tr><th>Where</th><th>Before</th><th>Now</th><th>What to do</th></tr></thead><tbody>
<tr><td>[[GET /users/profile/get/]]</td><td>Returned any user's profile incl. <code>access_token</code></td><td>Self: full profile without token. Others: <code>userId, name, role</code> only</td><td>Treat other fields as optional; never expect a token</td></tr>
<tr><td>[[PUT /users/profile/update/]]</td><td>Could change email/phone directly</td><td>400 if email/phone differ from the current values</td><td>Send only <code>name</code>/<code>fcm_token</code>; use the contact-change OTP flow</td></tr>
<tr><td>[[POST /artists/documents/create/]] <small>(new on the server — if the app was built for Aadhaar-only)</small></td><td>Aadhaar number + one image</td><td>ID proofs need <code>id_type</code>, <code>document_number</code>, and <code>back_file</code> (most types)</td><td>New KYC form, see flow</td></tr>
<tr><td>[[GET /artists/documents/get_all/]] / [[GET /artists/documents/get/]] <small>(new on the server)</small></td><td>If the app expects <code>fileUrl</code> to be an image URL and the number in clear</td><td><code>fileUrl</code> = API route needing the Bearer header; number masked</td><td>Fetch files with auth and show as blob</td></tr>
<tr><td>Registration endpoints</td><td><code>role</code> could be <code>admin</code>; any 8+ char password</td><td>Only <code>customer</code>/<code>artist</code>; weak passwords rejected</td><td>Show the validation error from <code>error[0].password</code></td></tr>
<tr><td>Login / OTP verify / refresh</td><td>Deactivated users still got tokens</td><td>HTTP 403 “This account is deactivated”</td><td>Handle 403 as “account disabled”</td></tr>
</tbody></table></div>

<h3 id="behaviour">Behaviour changes that need UI work</h3>
<ul>
 <li><b>Prices are server-side.</b> A booking total = package price + selected add-ons + travel fee. Show the returned <code>total_amount</code>; do not compute or send it.</li>
 <li><b>Booking slots now include travel/return buffers</b> for Home Visits (see availability endpoint).</li>
 <li><b>Approval is stricter:</b> artist needs display name, date of birth, profile type, ≥1 work sample, services, a package, a location type, a weekly schedule, an ID proof, a bank account and the accepted agreement. An admin must verify the ID proof before approving.</li>
 <li><b>Editing services no longer un-approves</b> an artist.</li>
 <li><b>Customers cannot cancel</b> once the artist has arrived or the service is running.</li>
 <li><b>Refunds are real:</b> cancelling a paid booking asks the payment gateway to refund; the customer receives a notification either way.</li>
 <li><b>An artist can't book their own services.</b></li>
 <li><b>Notifications</b> have new <code>type</code> values — see <a href="#enums">Values &amp; limits</a>.</li>
</ul>
"""


def changes_html(ops, new_routes, schema):
    """Static tables above + generated lists of every NEW and CHANGED endpoint, grouped by area."""
    by_tag = {}
    for path, method, op in ops:
        by_tag.setdefault(op['tags'][0], []).append((path, method))
    def anchor(path, method):
        return '#' + method.lower() + '-' + re.sub(r'[^a-z0-9]+', '-', path.lower()).strip('-')
    new_rows, changed_rows = [], []
    for title, tags in TAG_GROUPS:
        for tag in tags:
            for path, method in sorted(by_tag.get(tag, [])):
                link = f'<a class="eplink" href="{anchor(path, method)}"><b>{method.upper()}</b> {path}</a>'
                if path in new_routes:
                    new_rows.append((title, link, ''))
                if path in CHANGED and path not in new_routes:
                    changed_rows.append((title, link, CHANGED[path][1], CHANGED[path][0]))
    def tr(cells):
        return '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'
    new_html = ''.join(tr((t, l)) for t, l, _ in new_rows)
    chg_html = ''.join(tr((t, l + (' <span class="b b-brk">BREAKING</span>' if k == B else ''), note)) for t, l, note, k in changed_rows)
    return (CHANGES_STATIC +
            f'<h3 id="new-endpoints">All new endpoints ({len(new_rows)})</h3><div class="tablewrap"><table><thead><tr><th>Area</th><th>Endpoint</th></tr></thead><tbody>{new_html}</tbody></table></div>'
            f'<h3 id="changed-endpoints">All changed existing endpoints ({len(changed_rows)})</h3><div class="tablewrap"><table><thead><tr><th>Area</th><th>Endpoint</th><th>What changed</th></tr></thead><tbody>{chg_html}</tbody></table></div>')


CONVENTIONS = """
<h3 id="c-basics">Basics</h3>
<ul>
 <li><b>Base URL:</b> <code>{BASE_URL}</code> (per environment). Paths in this guide are relative to it. <b>Every path ends with a slash</b> — leave it out and the request fails.</li>
 <li><b>Auth:</b> <code>Authorization: Bearer &lt;access_token&gt;</code> on everything except the “PUBLIC” endpoints. Access token lives 7 days, refresh token 30 days.</li>
 <li><b>One session per user.</b> Logging in on another device (or re-logging in) makes the old access token invalid: the next call returns <b>401 “Invalid access token”</b>. Treat any 401 as “go to login”.</li>
 <li><b>Content types:</b> JSON endpoints take <code>application/json</code>. File endpoints take <code>multipart/form-data</code> (badge <span class="b b-mp">MULTIPART</span>). Other fields in a multipart request are plain form fields; send lists by repeating the field name.</li>
 <li><b>HTTP verbs:</b> <code>GET</code> reads (parameters in the query string), <code>POST</code> creates, <code>PUT</code> updates / performs an action (JSON body), <code>DELETE</code> deletes (id in the <b>query string</b>, no body).</li>
</ul>

<h3 id="c-envelope">Response envelope</h3>
<pre class="plain">Success:  { "status": true,  "message": "…",  "data": &lt;object | array | {data:[…], presentPage, totalPage}&gt; }
Failure:  { "status": false, "message": "…",  "error": ["…"] }</pre>
<ul>
 <li>Field names in <b>responses are camelCase</b> (<code>artistId</code>); field names in <b>requests are snake_case</b> (<code>artist_id</code>). Newly created ids come back in snake_case inside <code>data</code> (e.g. <code>{"booking_id": 41}</code>).</li>
 <li>Money is a <b>string with two decimals</b> (<code>"2500.00"</code>) in booking/package/add-on data, except the payment order amount which is an integer in <b>paise</b>.</li>
 <li>Ids are integers. Missing optional values are <code>null</code>.</li>
</ul>

<h3 id="c-dates">Dates, times and time zones</h3>
<table class="kv"><tbody>
<tr><td>Booking date in requests</td><td><code>DD-MM-YY</code>, e.g. <code>12-10-26</code> (create booking, availability, reschedule <code>proposed_date</code>, list <code>from_date</code>/<code>to_date</code>)</td></tr>
<tr><td>Block date, date of birth</td><td>Block date accepts <code>YYYY-MM-DD</code> or <code>DD-MM-YYYY</code>; <code>date_of_birth</code> is <code>YYYY-MM-DD</code></td></tr>
<tr><td>Times</td><td><code>HH:MM:SS</code> (24-hour), e.g. <code>10:00:00</code></td></tr>
<tr><td>Booking date/time meaning</td><td><b>India Standard Time wall-clock</b> (what the customer sees on the clock). Don't convert it.</td></tr>
<tr><td>Timestamps in responses</td><td>ISO-8601 in UTC, e.g. <code>2026-10-12T10:00:00+00:00</code>; convert for display</td></tr>
<tr><td>Dates in responses</td><td><code>YYYY-MM-DD</code></td></tr>
</tbody></table>

<h3 id="std-list">Standard list parameters</h3>
<p>Every “get_all” endpoint is paginated and accepts these query parameters (all optional):</p>
<table class="kv"><tbody>
<tr><td><code>page_num</code></td><td>Page, starting at 1 (a page beyond the last returns 400 “Page limit exceeded!”)</td></tr>
<tr><td><code>limit</code></td><td>Items per page (default 10)</td></tr>
<tr><td><code>sort_by</code> / <code>sort_order</code></td><td>A response field name (camelCase) and <code>asc</code>|<code>desc</code>. Default order is <code>asc</code>, so ask for <code>desc</code> explicitly for “newest first”. Unknown fields are ignored.</td></tr>
<tr><td><code>filter_key</code> / <code>filter_value</code></td><td>Filter by a response field name; endpoints that support a specific filter say so (e.g. <code>filter_key=status</code>, <code>bookingId</code>)</td></tr>
<tr><td><code>search_key</code></td><td>Free-text search (what is searched depends on the endpoint)</td></tr>
<tr><td><code>from_date</code> / <code>to_date</code></td><td><code>DD-MM-YY</code>, where supported</td></tr>
<tr><td><code>values</code></td><td>Comma-separated field names to return a subset. <b>Avoid:</b> several endpoints validate the full shape and reject subsets.</td></tr>
<tr><td><code>artist_id</code></td><td>On artist-owned lists: read an approved artist's public data instead of your own</td></tr>
</tbody></table>
<pre class="plain">{ "status": true, "message": "Data fetched successfully",
  "data": { "data": [ … ], "presentPage": 1, "totalPage": 3,
            "nextPageUrl": "https://…?page_num=2", "previousPageUrl": null } }</pre>
<p>Only present when there is more than one page: <code>nextPageUrl</code>, <code>previousPageUrl</code>.</p>

<h3 id="c-files">Files and images</h3>
<ul>
 <li><b>Public images</b>: profile/cover photo (<code>profilePhotoUrl</code>, <code>coverPhotoUrl</code>) and package photo (<code>photoUrl</code>) come back as <b>absolute URLs</b> (or <code>null</code>) — use them directly. <b>Portfolio items are the exception:</b> <code>fileUrl</code> is a storage path like <code>portfolios/artist_7/abc.png</code>, so the image is <code>{BASE_URL}/media/&lt;fileUrl&gt;</code>. Admin review photos start with <code>/media/</code> — prepend the base URL. The public share page already returns absolute URLs.</li>
 <li><b>Private files</b> (KYC documents, ticket attachments) are <b>never public</b>. The API returns a route such as <code>/artists/documents/file/?document_id=9</code>; request it with the Bearer header and render the bytes (blob / memory image).</li>
 <li>Uploads are inspected on the server: the content must really be a JPEG/PNG/WEBP image (or PDF where allowed), the extension must match, and the size limit applies. Failures are 400 with a message — show it.</li>
</ul>

<h3 id="c-money">Money you may show</h3>
<ul>
 <li><b>Customer</b> sees <code>totalAmount</code> (includes add-ons and <code>travelFee</code>). Never shown to customers: <code>platformFee</code>, <code>netAmount</code>.</li>
 <li><b>Artist</b> sees <code>platformFee</code> (commission) and <code>netAmount</code> on each booking (fixed when the booking was made; <code>null</code> on older bookings).</li>
 <li>There is no earnings/payout screen data yet.</li>
</ul>

<h3 id="c-retry">Retries and double taps</h3>
<ul>
 <li>Booking creation is not idempotent by itself, but a second identical request is refused (“This slot is already booked”).</li>
 <li>Payment initiate <i>is</i> idempotent for the same amount (HTTP 200 with the same order). Payment verify is idempotent.</li>
 <li>Once-only codes (OTPs, booking OTP, PINs) are consumed on success; 5 wrong tries lock the code or account for 30 minutes (message “Account locked. Please try again after 30 minutes”).</li>
</ul>
"""


FLOWS = r"""
<p class="lead">Each flow lists the calls in order. Click an endpoint to jump to its full reference (fields, limits, examples).</p>
<nav class="flowindex">
  <a href="#flow-auth">1 · Sign-in &amp; passwords</a><a href="#flow-onboarding">2 · Artist onboarding &amp; approval</a><a href="#flow-kyc">3 · KYC &amp; bank</a>
  <a href="#flow-booking">4 · Booking (customer)</a><a href="#flow-payment">5 · Payment &amp; refunds</a><a href="#flow-lifecycle">6 · Booking day (artist)</a>
  <a href="#flow-reschedule">7 · Reschedule</a><a href="#flow-artist-tools">8 · Artist tools</a><a href="#flow-contact">9 · Change email / phone</a>
  <a href="#flow-support">10 · Support, chat &amp; notifications</a><a href="#flow-admin">11 · Admin screens</a>
</nav>

<section class="flow" id="flow-auth"><h3>1 · Sign-in, passwords and sessions</h3>
<ol>
 <li><b>Register</b> — [[POST /auth/register/]] with <code>name</code>, <code>phone_number</code> or <code>email</code>, <code>password</code>, <code>role</code> (<code>customer</code>|<code>artist</code>). Registering as an artist creates the artist profile automatically (exactly one).</li>
 <li><b>Or sign in with a code</b> — [[POST /auth/phone-otp/request/]] (add <code>role</code> only for a first-time user) then [[POST /auth/phone-otp/verify/]]. Email twin: [[POST /auth/email-otp/request/]] / [[POST /auth/email-otp/verify/]]. Codes are 6 digits, valid 10 minutes, single-use; 5 wrong tries lock the account for 30 minutes (403).</li>
 <li><b>Password login</b> — [[POST /auth/login/]] with <code>username</code> (email or phone) and <code>password</code>. <b>Google</b> — [[POST /auth/google/]].</li>
 <li>Every successful sign-in returns, inside <code>data</code>: <code>user_id, name, email, phone_number, role, fcm_token, access_token, refresh_token</code>. Store both tokens securely.</li>
 <li><b>Keep the session alive</b> — before the access token expires call [[POST /auth/token/refresh/]] with the <code>refresh_token</code>; you get a new pair (old ones stop working).</li>
 <li><b>Forgot password</b> — [[POST /auth/forgot-password/]] (<code>username</code>) → always 200 → user enters the code → [[POST /auth/reset-password/]] (<code>username, otp, new_password</code>). The password rules are the same as registration. After success all sessions are revoked: go to login.</li>
</ol>
<div class="callout"><b>Handle these:</b> 401 anywhere → clear tokens, show login · 403 on sign-in → account deactivated (or locked 30 min after too many wrong codes) · 400 with <code>error[0].password</code> → weak password (show it).</div>
</section>

<section class="flow" id="flow-onboarding"><h3>2 · Artist onboarding and approval</h3>
<p>The artist is shown a checklist from [[GET /artists/onboarding/status/]]. Each key in <code>steps</code> turns <code>true</code> when it is done; when all are true the artist can submit.</p>
<table class="kv"><thead><tr><th>steps key</th><th>What completes it</th><th>Calls</th></tr></thead><tbody>
<tr><td><code>basicInfo</code></td><td>name, bio and city set</td><td>[[PUT /users/profile/update/]] (<code>name</code>), [[PUT /artists/profile/update/]] (<code>bio</code>, <code>city</code>)</td></tr>
<tr><td><code>registrationFields</code></td><td><code>display_name</code>, <code>date_of_birth</code> (18+), <code>profile_type</code> (instagram link & experience are optional)</td><td>[[PUT /artists/profile/update/]] — also <code>years_experience</code>, <code>instagram_url</code></td></tr>
<tr><td><code>location</code></td><td>a base address</td><td>[[POST /users/address/create/]] then [[PUT /artists/profile/update/]] with <code>base_address_id</code></td></tr>
<tr><td><code>services</code></td><td>at least one <b>active package</b></td><td>[[POST /artists/services/add/]] (which services the artist offers) and [[POST /artists/packages/create/]]</td></tr>
<tr><td><code>availability</code></td><td>an active weekly schedule <b>and</b> a location type</td><td>[[POST /artists/availability/schedule/set/]] and [[POST /artists/locations/add/]]</td></tr>
<tr><td><code>workSamples</code></td><td>≥ 1 work-sample photo (max 5)</td><td>[[POST /artists/portfolio/create/]] with <code>is_work_sample=true</code></td></tr>
<tr><td><code>documents</code></td><td>an ID proof</td><td>see <a href="#flow-kyc">KYC</a></td></tr>
<tr><td><code>payoutAccount</code></td><td>bank account saved</td><td>[[PUT /artists/payout_account/set/]]</td></tr>
<tr><td><code>agreement</code></td><td>Terms &amp; Privacy accepted</td><td>[[PUT /artists/profile/agreement/accept/]] (get the links from [[GET /core/pages/get/]])</td></tr>
</tbody></table>
<p>Nice-to-haves that are not required to submit: profile/cover photo [[PUT /artists/profile/photo/upload/]], specialities [[PUT /artists/profile/specialities/set/]] (must be a subset of the services the artist offers, max 10), package extras/photo, add-ons, service areas.</p>
<h4>Submit, review, feedback, resubmit</h4>
<ol>
 <li>[[POST /artists/onboarding/submit/]] — 400 with the list of unfinished steps if something is missing. On success <code>status</code> becomes <code>submitted</code>.</li>
 <li>Admin reviews (see <a href="#flow-admin">Admin screens</a>): either <b>approves</b> (<code>status: approved</code>, the artist is now searchable and bookable) or <b>rejects with a reason</b> (<code>status: rejected</code>). The artist gets a notification (<code>artist_approved</code> / <code>artist_rejected</code>).</li>
 <li>The artist reads the admin's message in <code>latestFeedback</code> of [[GET /artists/onboarding/status/]] or the full history from [[GET /artists/review/feedback/get_all/]] (oldest first; add <code>sort_order=desc</code> for newest first).</li>
 <li>After a rejection the artist fixes things and calls [[POST /artists/onboarding/submit/]] again (resubmit) — it goes back to <code>submitted</code>.</li>
 <li>Once <code>approved</code>, editing services, packages, photos etc. does <b>not</b> take the profile offline.</li>
</ol>
<div class="callout">The “changes required” state is shown with <code>status: "rejected"</code> plus the admin's message — there is no separate status value.</div>
</section>

<section class="flow" id="flow-kyc"><h3>3 · KYC documents and bank account</h3>
<h4>ID proof</h4>
<table class="kv"><thead><tr><th><code>id_type</code></th><th><code>document_number</code> format</th><th>Back image</th></tr></thead><tbody>
<tr><td><code>aadhaar</code></td><td>12 digits, may contain spaces; cannot start with 0 or 1</td><td>required</td></tr>
<tr><td><code>voter_id</code></td><td>3 letters + 7 digits (e.g. <code>ABC1234567</code>)</td><td>required</td></tr>
<tr><td><code>passport</code></td><td>letter + 7 digits (e.g. <code>K1234567</code>)</td><td>optional</td></tr>
<tr><td><code>driving_licence</code></td><td>e.g. <code>MH12-2011-0012345</code> (state + RTO + year + 7 digits; spaces/hyphens allowed)</td><td>required</td></tr>
</tbody></table>
<ol>
 <li>[[POST /artists/documents/create/]] (multipart): <code>document_type=id_proof</code>, <code>id_type</code>, <code>document_number</code>, <code>file</code>, <code>back_file</code> as required above. Other <code>document_type</code>s (<code>address_proof</code>, <code>certification</code>) take just <code>file</code>.</li>
 <li>The artist may have <b>one</b> ID proof: sending a new one replaces the old one and resets it to pending.</li>
 <li>List with [[GET /artists/documents/get_all/]]. Each item has <code>idType</code>, a <b>masked</b> <code>documentNumber</code> (e.g. <code>XXXXXXXX9012</code>), <code>verificationStatusId</code> (look up the name with [[GET /core/approval-status/get_all/]]: pending → verified = approved / rejected), <code>rejectionReason</code>, <code>fileUrl</code>, <code>backFileUrl</code>.</li>
 <li>To <b>display</b> a document call the <code>fileUrl</code> (relative to the base URL) with the Bearer header and show the returned bytes. [[GET /artists/documents/file/]]</li>
 <li>When an admin rejects a document the artist gets a <code>document_rejected</code> notification and <code>rejectionReason</code> is filled — ask for a re-upload. When approved: <code>document_approved</code>.</li>
</ol>
<pre class="plain">POST /artists/documents/create/      (multipart/form-data)
document_type=id_proof  id_type=aadhaar  document_number=2345 6789 0123
file=@front.jpg  back_file=@back.jpg</pre>
<p>Privacy: the full number is never returned to the app (Aadhaar is not even stored in full). Don't log or cache the document images.</p>
<h4>Bank account</h4>
<ol>
 <li>[[PUT /artists/payout_account/set/]]: <code>account_holder_name</code>, <code>bank_account_number</code> (6–30 digits), <code>ifsc_code</code> (e.g. <code>HDFC0001234</code>), optional <code>upi_id</code>. Saves or replaces the single account; changing it resets verification to pending.</li>
 <li>[[GET /artists/payout_account/get/]] shows <code>bankAccountNumberMasked</code> only. Nothing pays out yet.</li>
</ol>
</section>

<section class="flow" id="flow-booking"><h3>4 · Booking (customer app)</h3>
<ol>
 <li><b>Discover</b> — [[GET /customers/artists/search/]] (approved artists who are accepting bookings), then [[GET /customers/artists/get/]] for the artist page: <code>profile</code>, <code>packages</code> (with extras and category), <code>portfolio</code> (artist's order), <code>services</code>, <code>addOns</code> (each lists the <code>packageIds</code> it applies to) and <code>serviceAreas</code>. Show a “not accepting bookings” state when <code>profile.isAcceptingBookings</code> is false.</li>
 <li><b>Pick a day</b> — [[GET /customers/artists/availability/]] for that date (<code>booking_date=DD-MM-YY</code>). Offer only times that fit the rules in the endpoint note (working window, <code>blockedRanges</code>, buffers).</li>
 <li><b>Address</b> — for a <b>Home Visit</b> the customer needs a saved address ([[POST /users/address/create/]]). If the artist has service areas, the address <code>city</code> must match one of them (case-insensitive) and the area's travel charge is added.</li>
 <li><b>Create</b> — [[POST /customers/bookings/create/]]:
<pre class="plain">{ "artist_id": 7, "package_id": 7, "location_type_id": 1,
  "booking_date": "12-10-26", "start_time": "10:00:00",
  "address_id": 5, "addon_ids": [3], "notes": "Please bring HD kit" }</pre>
 The response gives <code>booking_id</code>, <code>total_amount</code>, <code>travel_fee</code>. The slot is <b>locked for 15 minutes</b> (<code>expiresAt</code> on the booking); if it is not paid in time the booking is cancelled automatically.
 The total = package + add-ons + travel fee; the appointment length = package duration + add-on durations.</li>
 <li><b>Pay</b> → next flow. After payment the artist confirms; the customer is notified (<code>booking_confirmed</code>).</li>
 <li><b>Follow the booking</b> — [[GET /customers/bookings/get/]] / [[GET /customers/bookings/get_all/]]. Map to screens with the table below.</li>
 <li><b>Cancel</b> — [[PUT /customers/bookings/cancel/]] is allowed while the booking is pending/confirmed <i>and the artist has not arrived</i>. A paid booking is refunded (see Payment).</li>
 <li><b>Review</b> — after completion [[POST /customers/reviews/create/]] (1–5 stars, once per booking). The artist may reply; the reply appears as <code>reply</code>/<code>repliedAt</code> in [[GET /customers/reviews/get_all/]].</li>
</ol>
<h4>Which screen to show</h4>
<table class="kv"><thead><tr><th>Booking state</th><th>How to tell (status name from <a href="#flow-support">core statuses</a> + timestamps)</th><th>Customer sees</th></tr></thead><tbody>
<tr><td>Awaiting payment / artist</td><td><code>pending</code></td><td>Pay now (countdown to <code>expiresAt</code>) / waiting for artist</td></tr>
<tr><td>Upcoming</td><td><code>confirmed</code>, <code>onMyWayAt</code> null</td><td>Details, reschedule requests, cancel</td></tr>
<tr><td>Artist on the way</td><td><code>confirmed</code>, <code>onMyWayAt</code> set, <code>arrivedAt</code> null</td><td>“On the way”</td></tr>
<tr><td>Artist arrived</td><td><code>confirmed</code>, <code>arrivedAt</code> set</td><td>Show the <b>Start PIN</b> ([[GET /customers/bookings/start_pin/]]) to tell the artist</td></tr>
<tr><td>In service</td><td><code>in_progress</code> (<code>serviceStartedAt</code>)</td><td>Show the <b>Completion PIN</b> ([[GET /customers/bookings/completion_pin/]])</td></tr>
<tr><td>Done</td><td><code>completed</code></td><td>Review prompt; cashback coins credited</td></tr>
<tr><td>Cancelled / missed</td><td><code>cancelled</code> / <code>no_show</code></td><td>Reason in <code>cancellationReason</code>, <code>cancelledBy</code></td></tr>
</tbody></table>
<h4>Refusals to handle (all HTTP 400, show <code>message</code>)</h4>
<ul class="tight">
 <li>“This slot is already booked” — overlap, including the artist's travel/return buffers → re-fetch availability.</li>
 <li>“The selected time slot is not available” — blocked day, outside working hours, or would run past midnight.</li>
 <li>“Bookings must be made at least 2 hours in advance” · “Cannot book a date in the past”.</li>
 <li>“You cannot book your own services” · “This artist is not accepting new bookings right now” · “This package is currently unavailable”.</li>
 <li>“One or more selected add-ons are not available for this package”.</li>
 <li>“The artist does not travel to the selected address city” · “An address is required for a home visit with this artist”.</li>
</ul>
</section>

<section class="flow" id="flow-payment"><h3>5 · Payment and refunds</h3>
<ol>
 <li>[[POST /customers/payments/initiate/]] with <code>booking_id</code> (full payment) — or with <code>amount</code> and <code>payment_type</code> = <code>advance</code>/<code>balance</code> for part payments. Optional <code>redemption_tier_id</code> to pay part with coins (tiers from [[GET /customers/wallet/eligible_tiers/]]).</li>
 <li>Open Razorpay Checkout with the returned <code>gateway_order_id</code>, <code>razorpay_key_id</code>, <code>amount</code> (paise), <code>currency</code>.
  If the response has <code>fully_covered_by_coins: true</code> there is nothing to pay — the payment is already settled.</li>
 <li>When Checkout succeeds call [[POST /customers/payments/verify/]] with <code>razorpay_order_id, razorpay_payment_id, razorpay_signature</code>. The server double-checks with Razorpay that the money was really captured.</li>
 <li>When the booking is fully paid the artist can confirm it. History: [[GET /customers/payments/get_all/]].</li>
</ol>
<div class="callout"><b>Rules that now exist</b><ul class="tight">
 <li>Tapping Pay twice returns the <b>same order</b> (HTTP 200 instead of 201) — use it, don't create another.</li>
 <li>If an open order already covers the dues, a different-amount order is refused: “A payment for this booking is already in progress…”. Open orders older than 30 minutes stop blocking.</li>
 <li>A booking can never be settled for more than its total. If a capture would exceed it, verify returns 400 “…exceed the booking total… will be refunded” and the payment is marked failed (support refunds the customer).</li>
 <li><b>Refunds:</b> when a paid booking is cancelled (by customer or artist) the server asks Razorpay to refund the cash portion and notifies the customer: <code>refund_initiated</code> (“a refund of ₹X has been initiated”) or <code>refund_pending</code> (“our team will complete the refund”). Coins used are returned to the wallet. Use neutral wording like “refund initiated” — settlement time depends on the bank.</li>
</ul></div>
</section>

<section class="flow" id="flow-lifecycle"><h3>6 · Booking day (artist app)</h3>
<ol>
 <li><b>Incoming</b> — the artist gets a <code>new_booking_alert</code> and a <code>booking_otp_issued</code> notification. The booking OTP (6 digits) is what they will enter on arrival. [[GET /artists/bookings/get_all/]] lists bookings; each shows <code>platformFee</code>, <code>netAmount</code>, <code>addOns</code>, <code>travelFee</code>.</li>
 <li><b>Accept or decline</b> — [[PUT /artists/bookings/update_status/]] with <code>status=confirmed</code> (only after the customer has paid in full; otherwise 400 “…cannot be confirmed until payment has been completed”) or <code>status=cancelled</code> + <code>reason</code> (decline/cancel; a paid booking is refunded).</li>
 <li><b>On my way</b> — [[PUT /artists/bookings/on_my_way/]], only within <b>2 hours before the start</b>.</li>
 <li><b>Arrived</b> — [[PUT /artists/bookings/arrived/]] with the <code>booking_otp</code>. Wrong codes are counted (5 → locked 30 min).</li>
 <li><b>Start</b> — the customer reads their Start PIN; the artist enters it in [[PUT /artists/bookings/start_pin/verify/]] → booking becomes <code>in_progress</code>.</li>
 <li><b>Finish</b> — the customer reads their Completion PIN; the artist enters it in [[PUT /artists/bookings/completion_pin/verify/]] → <code>completed</code> (cashback is credited to the customer once).</li>
 <li><b>After</b> — rate the customer with [[POST /artists/customer_reviews/create/]] (once per completed booking; private to artists), and reply to the customer's review with [[PUT /artists/reviews/reply/]].</li>
</ol>
<p>Steps cannot be skipped or repeated (each returns 400 with a message such as “Artist must be marked as on the way…”). A booking nobody acts on is marked <code>no_show</code> automatically 2 hours after its start.</p>
</section>

<section class="flow" id="flow-reschedule"><h3>7 · Reschedule</h3>
<ol>
 <li><b>Artist proposes</b> — [[POST /artists/bookings/reschedule/request/]] (<code>booking_id</code>, <code>proposed_date</code> DD-MM-YY, <code>proposed_start_time</code>, optional <code>reason</code>). Only <code>confirmed</code> bookings the artist has not yet set off for. One open request per booking. The new slot must pass all booking rules (hours, blocked days, overlaps incl. buffers, at least 2 h ahead).</li>
 <li><b>Customer is notified</b> (<code>reschedule_requested</code>) and sees it in [[GET /customers/bookings/reschedule/get_all/]] (use <code>filter_key=bookingId&amp;filter_value=…</code>): <code>previous*</code> and <code>proposed*</code> date/times, <code>status</code> (<code>pending</code>), <code>expiresAt</code>.</li>
 <li><b>Customer answers</b> — [[PUT /customers/bookings/reschedule/respond/]] with <code>decision=accepted|rejected</code>. Accepting moves the booking (the slot is re-checked at that moment; if it has been taken the call fails with 400 and the request stays pending so they can reject it). The artist is notified (<code>reschedule_accepted</code>/<code>_rejected</code>).</li>
 <li><b>Artist can withdraw</b> — [[PUT /artists/bookings/reschedule/cancel/]]. Artist's list: [[GET /artists/bookings/reschedule/get_all/]].</li>
 <li>A request lapses to <code>expired</code> after 24 h (or at the original start); cancelling the booking closes it (<code>cancelled</code>). A decided request can't be answered again.</li>
</ol>
</section>

<section class="flow" id="flow-artist-tools"><h3>8 · Artist tools</h3>
<table class="kv"><thead><tr><th>Feature</th><th>Calls</th><th>Notes</th></tr></thead><tbody>
<tr><td>Add-ons</td><td>[[POST /artists/addons/create/]] · [[PUT /artists/addons/update/]] · [[DELETE /artists/addons/delete/]] · [[GET /artists/addons/get_all/]]</td><td><code>package_ids</code> = the artist's own packages it applies to; <code>duration_minutes</code> extends the appointment; deleting never changes existing bookings</td></tr>
<tr><td>Service areas &amp; travel charge</td><td>[[POST /artists/service_areas/add/]] · [[PUT /artists/service_areas/update/]] · [[DELETE /artists/service_areas/remove/]] · [[GET /artists/service_areas/get_all/]]</td><td><code>travel_charge_type</code> <code>free</code> or <code>per_visit</code> (+ <code>charge_amount</code>). Per-km isn't available. With at least one active area, Home Visits only work for those cities</td></tr>
<tr><td>Travel / return buffers</td><td>[[PUT /artists/profile/update/]] <code>travel_time_before_minutes</code>, <code>return_buffer_minutes</code></td><td>Apply to Home Visits; block neighbouring time</td></tr>
<tr><td>Package extras</td><td>[[POST /artists/packages/create/]], [[PUT /artists/packages/photo/upload/]], [[DELETE /artists/packages/photo/delete/]]</td><td><code>makeup_type</code>, <code>brands</code> (free text), <code>product_details</code>, photo</td></tr>
<tr><td>Brands</td><td>[[GET /core/brands/get_all/]] · [[POST /artists/brands/request/]] · [[GET /artists/brands/requests/get_all/]]</td><td>Offer the list as suggestions; “request a brand” when missing (max 5 pending). Package <code>brands</code> stays free text</td></tr>
<tr><td>Accepting bookings switch</td><td>[[PUT /artists/profile/accepting_bookings/]]</td><td>Off = hidden from search and unbookable; existing bookings unaffected</td></tr>
<tr><td>Share profile</td><td>[[GET /artists/profile/share_link/]] → open [[GET /public/artists/get/]]</td><td>Stable link; public page shows only public data of approved artists</td></tr>
<tr><td>Portfolio order</td><td>[[PUT /artists/portfolio/reorder/]]</td><td>Send ids in the order wanted; unlisted items follow</td></tr>
<tr><td>My Clients</td><td>[[GET /artists/clients/get_all/]] · [[PUT /artists/clients/note/set/]]</td><td>Customers with a confirmed/started/completed booking; notes are private to the artist (blank note deletes it); <code>sort_by</code> <code>name|lastBookingDate|bookingsCount</code></td></tr>
<tr><td>Reviews</td><td>[[GET /artists/reviews/get_all/]] · [[PUT /artists/reviews/reply/]]</td><td>Replying again edits the reply</td></tr>
<tr><td>Insights</td><td>[[GET /artists/insights/summary/]]</td><td>Bookings by status, repeat clients, top services, lifetime profile views; optional <code>from_date</code>/<code>to_date</code>. <b>No earnings yet</b></td></tr>
</tbody></table>
</section>

<section class="flow" id="flow-contact"><h3>9 · Change email or phone number</h3>
<ol>
 <li>[[POST /users/contact/change/request/]] with <b>one</b> of <code>email</code> / <code>phone_number</code>. A 6-digit code is sent to the <i>new</i> contact (valid 10 min; one request per minute).</li>
 <li>User types the code → [[POST /users/contact/change/verify/]] with <code>otp</code>. On success the contact is replaced (the old one stops working for login). 5 wrong codes burn the code — request a new one. If someone else registered that contact in the meantime you get 400.</li>
 <li>[[PUT /users/profile/update/]] is for <code>name</code> and <code>fcm_token</code> only.</li>
</ol>
</section>

<section class="flow" id="flow-support"><h3>10 · Support, chat and notifications</h3>
<ul>
 <li><b>Tickets</b> (customers and artists): [[POST /help_center/tickets/create/]] (multipart: <code>issue_type, subject, description</code>, optional <code>booking_id</code> that belongs to the user, up to 5 <code>attachments</code>) · [[GET /help_center/tickets/get_all/]] (filters: <code>filter_key=status|bookingId|issueType</code>) · [[GET /help_center/tickets/get/]] · [[PUT /help_center/tickets/close/]]. Attachments are private: fetch <code>attachments[].url</code> with the Bearer header ([[GET /help_center/tickets/attachment/]]). Statuses: open → in_progress → resolved → closed; the admin's <code>resolutionNote</code> and a <code>support_ticket_update</code> notification arrive when it changes. Max 10 open tickets per user.</li>
 <li><b>Live help chat</b> (one running conversation per user, unchanged): customer [[GET /help_center/conversation/get/]], [[POST /help_center/messages/create/]]; artist the <code>/help_center/artist/…</code> twins.</li>
 <li><b>Booking chat</b> (unchanged): [[GET /chat/conversation/get/]], [[GET /chat/messages/get_all/]], [[POST /chat/messages/create/]] — only the booking's customer and artist; closed after completion.</li>
 <li><b>Notifications</b>: [[GET /notifications/get_all/]], [[PUT /notifications/mark_read/]], [[PUT /notifications/mark_all_read/]]. Use <code>type</code> to deep-link (see the list in <a href="#enums">Values</a>). Push (FCM) delivery is not configured yet — rely on this list / polling for now.</li>
 <li><b>Reference data</b> (cache it): [[GET /core/booking-status/get_all/]], [[GET /core/payment-status/get_all/]], [[GET /core/approval-status/get_all/]], [[GET /core/service-category/get_all/]], [[GET /core/service-sub-category/get_all/]], [[GET /core/location-type/get_all/]], [[GET /core/pages/get/]] (Terms, Privacy, Contact — public, <code>null</code> until configured).</li>
</ul>
</section>

<section class="flow" id="flow-admin"><h3>11 · Admin screens</h3>
<p>Admin accounts sign in through the normal sign-in endpoints; they can only be created on the server side, never through the app.</p>
<ol>
 <li><b>Review queue</b> — [[GET /admin-panel/artists/review_queue/get_all/]] (artists who submitted for review).</li>
 <li><b>Artist details</b> — [[GET /admin-panel/artists/review/get/]] (registration fields, specialities, work-sample photo URLs; these <code>fileUrl</code>s start with <code>/media/</code> — prepend the base URL).</li>
 <li><b>KYC</b> — [[GET /admin-panel/artists/documents/get_all/]] shows the <i>full</i> ID number to admins; view images with [[GET /artists/documents/file/]] (admins are allowed); decide with [[PUT /admin-panel/artists/documents/verify/]] (<code>approved</code>, or <code>rejected</code> + reason). A decided document can't be changed.</li>
 <li><b>Decision</b> — [[PUT /admin-panel/artists/approve/]] (needs the ID proof verified first) or [[PUT /admin-panel/artists/reject/]] with a reason the artist will read.</li>
 <li><b>Brands</b> — [[POST /admin-panel/brands/create/]], [[PUT /admin-panel/brands/update/]], requests [[GET /admin-panel/brands/requests/get_all/]] (<code>filter_key=status&amp;filter_value=pending</code>) and [[PUT /admin-panel/brands/requests/decide/]] (approving adds the brand).</li>
 <li><b>Support</b> — [[GET /help_center/admin/tickets/get_all/]], [[GET /help_center/admin/tickets/get/]], [[PUT /help_center/admin/tickets/update_status/]], plus the existing admin chat endpoints.</li>
</ol>
</section>
"""

ENUMS = """
<h3>Values you will send or receive</h3>
<table class="kv"><tbody>
<tr><td>Roles</td><td><code>customer</code>, <code>artist</code>, <code>admin</code> (admin is never selectable in the app)</td></tr>
<tr><td><code>profile_type</code></td><td><code>freelance</code>, <code>studio</code></td></tr>
<tr><td><code>document_type</code></td><td><code>id_proof</code>, <code>address_proof</code>, <code>certification</code></td></tr>
<tr><td><code>id_type</code></td><td><code>aadhaar</code>, <code>voter_id</code>, <code>passport</code>, <code>driving_licence</code></td></tr>
<tr><td>Approval / verification names</td><td><code>pending</code>, <code>approved</code>, <code>rejected</code>, <code>suspended</code> (ids from <code>/core/approval-status/get_all/</code>)</td></tr>
<tr><td>Onboarding <code>status</code></td><td><code>not_started</code>, <code>in_progress</code>, <code>submitted</code>, <code>approved</code>, <code>rejected</code>, <code>suspended</code></td></tr>
<tr><td>Booking status names</td><td><code>pending</code>, <code>confirmed</code>, <code>in_progress</code>, <code>completed</code>, <code>cancelled</code>, <code>no_show</code> (bookings carry <code>statusId</code>; map with <code>/core/booking-status/get_all/</code>)</td></tr>
<tr><td>Status values the artist may set</td><td><code>confirmed</code> (from pending, once paid), <code>cancelled</code> (from pending or confirmed), <code>no_show</code> (from in_progress). <code>in_progress</code> and <code>completed</code> only happen through the PIN calls</td></tr>
<tr><td>Payment <code>payment_type</code></td><td><code>full</code> (default), <code>advance</code>, <code>balance</code></td></tr>
<tr><td>Payment status names</td><td><code>pending</code>, <code>paid</code>, <code>failed</code>, <code>refunded</code>, <code>partially_refunded</code></td></tr>
<tr><td>Portfolio <code>media_type</code></td><td><code>image</code>, <code>video</code></td></tr>
<tr><td><code>travel_charge_type</code></td><td><code>free</code>, <code>per_visit</code> (<code>per_km</code> is rejected)</td></tr>
<tr><td>Location type that triggers travel rules</td><td>the one named <b>Home Visit</b> in <code>/core/location-type/get_all/</code></td></tr>
<tr><td>Reschedule <code>status</code></td><td><code>pending</code>, <code>accepted</code>, <code>rejected</code>, <code>cancelled</code>, <code>expired</code>; customer <code>decision</code>: <code>accepted</code>|<code>rejected</code></td></tr>
<tr><td>Ticket <code>issue_type</code></td><td><code>booking</code>, <code>payment</code>, <code>service_quality</code>, <code>account</code>, <code>technical</code>, <code>other</code></td></tr>
<tr><td>Ticket <code>status</code></td><td><code>open</code>, <code>in_progress</code>, <code>resolved</code>, <code>closed</code></td></tr>
<tr><td>Brand request <code>status</code></td><td><code>pending</code>, <code>approved</code>, <code>rejected</code></td></tr>
<tr><td>Feedback <code>decision</code></td><td><code>approved</code>, <code>rejected</code></td></tr>
</tbody></table>

<h3>Limits and timings</h3>
<table class="kv"><tbody>
<tr><td>Images</td><td>JPEG / PNG / WEBP, ≤ 5 MB. KYC and ticket attachments may also be PDF. Portfolio video: mp4 / mov / webm ≤ 50 MB</td></tr>
<tr><td>Portfolio</td><td>20 active items; 5 work samples (separate pool)</td></tr>
<tr><td>Specialities</td><td>max 10, from the services the artist offers</td></tr>
<tr><td>Package</td><td>price ≥ 500; brands ≤ 10 names (50 chars each); <code>makeup_type</code> ≤ 50 chars</td></tr>
<tr><td>Add-on</td><td>price ≥ 1, extra duration 0–480 min, ≤ 50 linked packages</td></tr>
<tr><td>Saved addresses</td><td>5 per customer, one default</td></tr>
<tr><td>Chat message</td><td>≤ 2000 characters</td></tr>
<tr><td>Ticket</td><td>subject ≤ 150, description ≤ 2000, ≤ 5 attachments, ≤ 10 open tickets</td></tr>
<tr><td>Brand requests</td><td>5 pending per artist</td></tr>
<tr><td>Passwords</td><td>≥ 8 characters, not purely numeric, not a common password</td></tr>
<tr><td>Date of birth</td><td>artist must be at least 18</td></tr>
<tr><td>Booking</td><td>≥ 2 h ahead; slot locked 15 min until paid; on-my-way within 2 h before start; auto no-show 2 h after start</td></tr>
<tr><td>Codes (OTP / PIN)</td><td>login OTP and contact-change OTP: 6 digits, 10 min, 5 wrong tries → locked; booking OTP: 6 digits; Start/Completion PIN: 4 digits; all single-use</td></tr>
<tr><td>Reschedule</td><td>answer window 24 h; one open request per booking</td></tr>
<tr><td>Tokens</td><td>access 7 days, refresh 30 days, one session per user</td></tr>
<tr><td>Commission</td><td>default 10 % (per artist; the rate in force when the booking was made is the one applied)</td></tr>
</tbody></table>

<h3>Notification <code>type</code> values</h3>
<p><b>New in this release:</b> <code>reschedule_requested</code>, <code>reschedule_accepted</code>, <code>reschedule_rejected</code>, <code>reschedule_cancelled</code>,
<code>document_approved</code>, <code>document_rejected</code>, <code>artist_approved</code>, <code>artist_rejected</code>, <code>review_reply</code>,
<code>brand_request_approved</code>, <code>brand_request_rejected</code>, <code>support_ticket_update</code>, <code>contact_changed</code>,
<code>payout_account_changed</code>, <code>refund_initiated</code>, <code>refund_pending</code>.<br>
<b>Existing:</b> <code>new_booking_alert</code>, <code>booking_otp_issued</code>, <code>booking_confirmed</code>, <code>booking_cancelled</code>, <code>booking_completed</code>,
<code>booking_no_show</code>, <code>artist_on_the_way</code>, <code>artist_arrived</code>, <code>start_pin_ready</code>, <code>service_started</code>, <code>completion_pin_ready</code>,
<code>booking_reminder_24h</code>, <code>booking_reminder_2h</code>, <code>payment_status</code> (and others from the wallet module).
Each notification has <code>bookingId</code> when it relates to a booking.</p>
"""

ERRORS = """
<h3>Shapes</h3>
<table class="kv"><tbody>
<tr><td>Business rule broken</td><td>HTTP <b>400</b> <code>{"status": false, "message": "Value Error &lt;text&gt;", "error": ["&lt;text&gt;"]}</code> — show <code>error[0]</code></td></tr>
<tr><td>Field validation</td><td>HTTP <b>400</b> <code>{"status": false, "message": "Validation Error", "error": [{"city": ["This field may not be blank."], "pin_code": ["This field is required."]}]}</code> — <code>error[0]</code> is an object keyed by field name</td></tr>
<tr><td>Body is not a JSON object</td><td>HTTP 400 validation error (“The request body must be a JSON object”)</td></tr>
<tr><td>Not logged in / bad token</td><td>HTTP <b>401</b> <code>{"detail": "Invalid access token"}</code> (also “Authentication credentials were not provided.”, “Expired access token”) — note: <b>not</b> the standard envelope</td></tr>
<tr><td>Wrong credentials / bad OTP</td><td>HTTP 401 (login) or 400 (OTP) with the envelope</td></tr>
<tr><td>Account locked or deactivated</td><td>HTTP <b>403</b> with the envelope (“Account locked. Please try again after 30 minutes” / “This account is deactivated”)</td></tr>
<tr><td>Unknown user on OTP request without a role</td><td>HTTP 404 “User not found”</td></tr>
<tr><td>Wrong HTTP method</td><td>HTTP 405 <code>{"detail": "Method \\"DELETE\\" not allowed."}</code></td></tr>
<tr><td>Unexpected server problem</td><td>HTTP 400 with a generic message, or 5xx — show a retry message</td></tr>
</tbody></table>
<div class="callout"><b>“Forbidden” is a 400.</b> Using someone else's data or an admin endpoint as a normal user returns HTTP 400 with “Not allowed to access this resource” or “No matching record found” — not 403/404. Branch on the message text only where you have to; otherwise show it.</div>

<h3>Messages worth handling specially</h3>
<table class="kv"><thead><tr><th>Message</th><th>Where</th><th>Suggested handling</th></tr></thead><tbody>
<tr><td>Invalid access token / Expired access token</td><td>any (401)</td><td>Clear session → login</td></tr>
<tr><td>Invalid or expired OTP</td><td>sign-in, reset, contact change</td><td>Let the user retry or resend</td></tr>
<tr><td>Account locked. Please try again after 30 minutes</td><td>OTP flows (403)</td><td>Disable the form, explain</td></tr>
<tr><td>This slot is already booked / The selected time slot is not available</td><td>create booking / reschedule</td><td>Reload availability</td></tr>
<tr><td>This booking cannot be confirmed until payment has been completed</td><td>artist confirm</td><td>Show “waiting for payment”</td></tr>
<tr><td>On My Way can only be marked within 2 hours of the booking start time</td><td>on-my-way</td><td>Disable the button until the window opens</td></tr>
<tr><td>A payment for this booking is already in progress…</td><td>initiate payment</td><td>Finish or wait for the open payment; don't retry blindly</td></tr>
<tr><td>This payment would exceed the booking total…</td><td>verify payment</td><td>Show “payment will be refunded”; refresh the booking</td></tr>
<tr><td>This booking can no longer be cancelled by the customer once the artist has arrived or the service has started</td><td>customer cancel</td><td>Hide the cancel button in those states</td></tr>
<tr><td>To change your email or phone number, request a verification code…</td><td>profile update</td><td>Route to the contact-change flow</td></tr>
<tr><td>Incomplete: &lt;step name&gt; (one entry per missing step)</td><td>onboarding submit</td><td><code>error</code> lists each missing step; highlight them</td></tr>
<tr><td>The artist has no verified ID proof; verify the identity document first</td><td>admin approve</td><td>Open the KYC panel</td></tr>
<tr><td>Only genuine JPEG, PNG or WEBP images are allowed / The uploaded file is too large</td><td>uploads</td><td>Show as-is</td></tr>
</tbody></table>
"""


# ───────────────────────── diagrams (rendered natively as mermaid by the artifact viewer) ─────────────────────────
FLOW_DIAGRAMS = {
    'flow-onboarding': r"""stateDiagram-v2
  [*] --> in_progress: register as artist
  in_progress --> submitted: all steps done, submit
  submitted --> approved: admin verifies ID, approves
  submitted --> rejected: admin rejects with a message
  rejected --> submitted: artist fixes things, resubmits
  approved --> [*]""",
    'flow-booking': r"""flowchart LR
  S["Search artists"] --> D["Artist page\npackages, add-ons, areas"]
  D --> A["Availability for a date\nblockedRanges + buffers"]
  A --> C["Create booking\nserver computes total"]
  C --> P["Pay within 15 min"]
  P --> K["Artist confirms"]
  K --> V["Booking day"]""",
    'flow-payment': r"""flowchart TD
  I["POST payments/initiate"] -->|"201 new order / 200 same open order"| R["Razorpay Checkout"]
  R --> V["POST payments/verify"]
  V -->|"captured, within total"| PD["paid"]
  V -->|"would exceed total"| F["400 + failed, refund by support"]
  PD --> CF["Artist can confirm"]
  CF -->|"booking cancelled later"| RF["Gateway refund requested"]""",
    'flow-lifecycle': r"""stateDiagram-v2
  [*] --> pending: customer creates, slot locked 15 min
  pending --> confirmed: artist accepts (after full payment)
  pending --> cancelled: declined, unpaid after 15 min, or customer cancels
  confirmed --> confirmed: on my way, then arrived (OTP)
  confirmed --> in_progress: start PIN
  in_progress --> completed: completion PIN
  confirmed --> cancelled: cancelled before the artist arrives
  confirmed --> no_show: nobody acted 2 h after start
  completed --> [*]""",
    'flow-reschedule': r"""stateDiagram-v2
  [*] --> pending: artist proposes a new time
  pending --> accepted: customer accepts, booking moves
  pending --> rejected: customer rejects
  pending --> cancelled: artist withdraws or booking cancelled
  pending --> expired: no answer in 24 h""",
}
