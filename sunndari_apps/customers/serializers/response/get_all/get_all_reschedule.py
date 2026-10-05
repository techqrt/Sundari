from rest_framework import serializers


class RescheduleSerializer(serializers.Serializer):
    rescheduleId = serializers.IntegerField()
    bookingId = serializers.IntegerField()
    requestedById = serializers.IntegerField()
    previousDate = serializers.DateField()
    previousStartTime = serializers.TimeField()
    previousEndTime = serializers.TimeField()
    proposedDate = serializers.DateField()
    proposedStartTime = serializers.TimeField()
    proposedEndTime = serializers.TimeField()
    reason = serializers.CharField(allow_null=True, allow_blank=True)
    status = serializers.ChoiceField(choices=['pending', 'accepted', 'rejected', 'cancelled', 'expired'])
    expiresAt = serializers.DateTimeField()
    respondedAt = serializers.DateTimeField(allow_null=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class RescheduleGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=RescheduleSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class RescheduleResponseGetAllSerializer(serializers.Serializer):
    data = RescheduleGetAllSerializer()
