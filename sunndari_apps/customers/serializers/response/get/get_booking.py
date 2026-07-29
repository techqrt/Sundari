from rest_framework import serializers


class BookingSerializer(serializers.Serializer):
    bookingId = serializers.IntegerField()
    customerId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    subCategoryId = serializers.IntegerField()
    packageId = serializers.IntegerField()
    locationTypeId = serializers.IntegerField()
    addressId = serializers.IntegerField(allow_null=True)
    bookingDate = serializers.DateField()
    startTime = serializers.TimeField()
    endTime = serializers.TimeField()
    statusId = serializers.IntegerField()
    totalAmount = serializers.DecimalField(max_digits=10, decimal_places=2)
    notes = serializers.CharField(allow_null=True)
    cancelledBy = serializers.CharField(allow_null=True)
    cancellationReason = serializers.CharField(allow_null=True)
    expiresAt = serializers.DateTimeField(allow_null=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class BookingResponseSerializer(serializers.Serializer):
    data = BookingSerializer()
