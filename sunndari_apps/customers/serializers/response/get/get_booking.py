from rest_framework import serializers


class BookingAddOnSerializer(serializers.Serializer):
    addOnId = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    durationMinutes = serializers.IntegerField()


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
    # totalAmount = package + add-ons + travelFee (computed server-side at booking time)
    travelFee = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    addOns = serializers.ListField(child=BookingAddOnSerializer(), required=False)
    # Artist-side only (never present in customer responses)
    platformFee = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    netAmount = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    travelMinutesBefore = serializers.IntegerField(allow_null=True, required=False)
    returnBufferMinutes = serializers.IntegerField(allow_null=True, required=False)
    notes = serializers.CharField(allow_null=True, allow_blank=True)
    cancelledBy = serializers.CharField(allow_null=True, allow_blank=True)
    cancellationReason = serializers.CharField(allow_null=True, allow_blank=True)
    expiresAt = serializers.DateTimeField(allow_null=True)
    onMyWayAt = serializers.DateTimeField(allow_null=True)
    arrivedAt = serializers.DateTimeField(allow_null=True)
    serviceStartedAt = serializers.DateTimeField(allow_null=True)
    serviceCompletedAt = serializers.DateTimeField(allow_null=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class BookingResponseSerializer(serializers.Serializer):
    data = BookingSerializer()
