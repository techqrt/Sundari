from rest_framework import serializers


class OnboardingStepsSerializer(serializers.Serializer):
    basicInfo = serializers.BooleanField()
    location = serializers.BooleanField()
    services = serializers.BooleanField()
    availability = serializers.BooleanField()
    registrationFields = serializers.BooleanField()
    workSamples = serializers.BooleanField()
    documents = serializers.BooleanField()
    payoutAccount = serializers.BooleanField()
    agreement = serializers.BooleanField()


class LatestFeedbackSerializer(serializers.Serializer):
    feedbackId = serializers.IntegerField()
    decision = serializers.ChoiceField(choices=['approved', 'rejected'])
    message = serializers.CharField(allow_blank=True)
    createdAt = serializers.DateTimeField()


class OnboardingStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=['not_started', 'in_progress', 'submitted', 'approved', 'rejected', 'suspended']
    )
    steps = OnboardingStepsSerializer()
    submittedForReviewAt = serializers.DateTimeField(allow_null=True)
    latestFeedback = LatestFeedbackSerializer(allow_null=True, required=False)


class OnboardingStatusResponseSerializer(serializers.Serializer):
    data = OnboardingStatusSerializer()
