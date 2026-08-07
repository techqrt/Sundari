class Constants:
    # Auth
    validation_error = 'Validation Error'
    auth_error = 'Authentication Error'
    server_error = 'Server Error'
    access_token_expired = 'Expired access token'
    refresh_token_invalid = 'Invalid refresh token'
    invalid_header = 'Invalid authorization header'
    auth_success = 'Authentication successful'
    invalid_access_token = 'Invalid access token'
    forbidden_access = 'Forbidden access'

    # OTP
    otp_sent = 'OTP sent successfully'
    otp_invalid = 'Invalid or expired OTP'
    otp_max_attempts = 'Maximum OTP attempts exceeded'
    account_locked = 'Account locked. Please try again after 30 minutes'

    # User
    mobile_number_not_unique = 'The mobile number already exists, please provide another mobile number'
    email_not_unique = 'The email already exists, please provide another email'
    user_not_found = 'User not found'
    user_already_exists = 'User already exists. Please login instead'

    # General
    page_num_exceeded = 'The given page number is greater than maximum available limit'
    delete_not_allowed = 'Deleting records is not allowed'
    update_not_allowed = 'Updating records is not allowed'
    item_not_found = 'Item not found'
    forbidden_resource = 'Not allowed to access this resource'
    data_get = 'Data fetched successfully'
    data_no_match = 'No matching record found'

    # Artist
    artist_not_found = 'Artist not found'
    artist_not_approved = 'Artist profile is not approved'
    artist_requires_package = 'Artist must have at least one active package'

    # Booking
    slot_unavailable = 'The selected time slot is not available'
    booking_not_found = 'Booking not found'
    booking_already_reviewed = 'This booking has already been reviewed'
    booking_not_completed = 'Review can only be submitted after the service is completed'
    slot_locked = 'Slot locked for 15 minutes pending payment'
    double_booking = 'This slot is already booked'

    # Payment
    payment_not_found = 'Payment record not found'
    payment_already_completed = 'Booking is already fully paid'
    invalid_payment_amount = 'Payment amount exceeds the remaining amount due'

    # Portfolio
    portfolio_limit_exceeded = 'Maximum 20 active portfolio items allowed'
    file_required = 'A file is required to create a portfolio item'

    # Address
    address_limit_exceeded = 'Maximum 5 saved addresses allowed'

    # Chat
    conversation_not_found = 'Conversation not found'
    conversation_closed = 'This conversation is closed and no longer accepts new messages'
    chat_not_eligible = 'Chat is only available for confirmed or in-progress bookings'
    message_empty = 'Message content cannot be empty'
