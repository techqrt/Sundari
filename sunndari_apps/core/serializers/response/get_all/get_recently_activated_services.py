from rest_framework import serializers


class RecentlyActivatedCategorySerializer(serializers.Serializer):
    categoryId = serializers.IntegerField()
    name = serializers.CharField()


class RecentlyActivatedServiceSerializer(serializers.Serializer):
    subCategoryId = serializers.IntegerField(help_text='Use with GET /customers/artists/search/?sub_category_id= to open the service')
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True, allow_blank=True)
    category = RecentlyActivatedCategorySerializer()
    activatedAt = serializers.DateTimeField(
        help_text='When this service last went live. Remember (subCategoryId, activatedAt) as "already shown": a service '
                  'that is switched off and on again gets a new activatedAt and is shown again.')


class RecentlyActivatedServicesResponseSerializer(serializers.Serializer):
    data = serializers.ListField(child=RecentlyActivatedServiceSerializer())
