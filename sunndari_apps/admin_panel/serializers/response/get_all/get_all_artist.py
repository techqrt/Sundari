from rest_framework import serializers


class ArtistAdminItemSerializer(serializers.Serializer):
    artistId = serializers.IntegerField()
    userId = serializers.IntegerField()
    fullName = serializers.CharField(allow_null=True, allow_blank=True)
    displayName = serializers.CharField(allow_null=True, allow_blank=True)
    phoneNumber = serializers.CharField(allow_null=True, allow_blank=True)
    city = serializers.CharField(allow_null=True, allow_blank=True)
    approvalStatus = serializers.CharField(allow_null=True)
    registrationFeePaid = serializers.BooleanField()
    registrationFeeExempt = serializers.BooleanField()
    registrationEligible = serializers.BooleanField()
    isAcceptingBookings = serializers.BooleanField()
    acceptingLockedByAdmin = serializers.BooleanField()
    visibleToCustomers = serializers.BooleanField()
    createdAt = serializers.DateTimeField()


class ArtistAdminGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ArtistAdminItemSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class ArtistAdminResponseGetAllSerializer(serializers.Serializer):
    data = ArtistAdminGetAllSerializer()
