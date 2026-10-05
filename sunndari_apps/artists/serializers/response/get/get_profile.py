from rest_framework import serializers


class ArtistProfileSerializer(serializers.Serializer):
    artistId = serializers.IntegerField()
    userId = serializers.IntegerField()
    profilePhotoUrl = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    coverPhotoUrl = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    displayName = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    instagramUrl = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    profileType = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    specialities = serializers.ListField(child=serializers.IntegerField(), required=False)
    # Own-profile only (private): never part of the public subset.
    isAcceptingBookings = serializers.BooleanField(required=False)
    publicSlug = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    profileViewCount = serializers.IntegerField(required=False)
    agreementVersion = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    travelTimeBeforeMinutes = serializers.IntegerField(required=False)
    returnBufferMinutes = serializers.IntegerField(required=False)
    dateOfBirth = serializers.DateField(allow_null=True, required=False)
    bio = serializers.CharField(allow_null=True, allow_blank=True)
    yearsExperience = serializers.IntegerField()
    city = serializers.CharField(allow_null=True, allow_blank=True)
    serviceRadiusKm = serializers.IntegerField()
    avgRating = serializers.DecimalField(max_digits=3, decimal_places=2)
    totalReviews = serializers.IntegerField()
    # Internal (own-profile only; omitted when another user views the artist)
    commissionRate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    approvalStatusId = serializers.IntegerField(allow_null=True, required=False)
    # Internal onboarding fields — not populated by cross-app views (e.g. customers'
    # get_artist_detail) that deliberately show a stripped-down profile of other artists.
    baseAddressId = serializers.IntegerField(allow_null=True, required=False)
    termsAcceptedAt = serializers.DateTimeField(allow_null=True, required=False)
    submittedForReviewAt = serializers.DateTimeField(allow_null=True, required=False)
    rejectionReason = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class ArtistProfileResponseSerializer(serializers.Serializer):
    data = ArtistProfileSerializer()
