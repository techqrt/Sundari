from rest_framework import serializers
from sunndari_apps.payments.dataclasses.request.create.initiate_group_payment import InitiateGroupPaymentRequest


class InitiateGroupPaymentSerializer(serializers.Serializer):
    # min_length=2 — a "group" checkout of exactly one booking is just /initiate/;
    # keeping that distinction explicit avoids two endpoints doing the same thing.
    booking_ids = serializers.ListField(child=serializers.IntegerField(), min_length=2)
    # Applies only to booking_ids[0] — see InitiateGroupPaymentView for why a group
    # checkout can only ever discount the one booking that absorbs the whole tier.
    redemption_tier_id = serializers.IntegerField(required=False)

    def create(self, validated_data) -> InitiateGroupPaymentRequest:
        return InitiateGroupPaymentRequest(**validated_data)
