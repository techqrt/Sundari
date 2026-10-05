from rest_framework import serializers


class BookedRangeSerializer(serializers.Serializer):
    startTime = serializers.TimeField()
    endTime = serializers.TimeField()


class WorkingWindowSerializer(serializers.Serializer):
    startTime = serializers.TimeField()
    endTime = serializers.TimeField()
    locationTypeId = serializers.IntegerField(allow_null=True)


class AvailabilitySerializer(serializers.Serializer):
    artistId = serializers.IntegerField()
    bookingDate = serializers.DateField()
    dayOfWeek = serializers.IntegerField()
    isBlocked = serializers.BooleanField()
    workingWindow = WorkingWindowSerializer(allow_null=True)
    bookedRanges = serializers.ListField(child=BookedRangeSerializer())
    blockedRanges = serializers.ListField(child=BookedRangeSerializer(), required=False)
    bufferBeforeMinutes = serializers.IntegerField(required=False)
    bufferAfterMinutes = serializers.IntegerField(required=False)


class AvailabilityResponseSerializer(serializers.Serializer):
    data = AvailabilitySerializer()
