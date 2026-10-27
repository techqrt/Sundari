from rest_framework import serializers


class RecentlyActivatedCategorySerializer(serializers.Serializer):
    categoryId = serializers.IntegerField()
    name = serializers.CharField()


class RecentlyActivatedServiceSerializer(serializers.Serializer):
    subCategoryId = serializers.IntegerField(help_text='Pass as sub_category_id to POST /artists/services/add/ to add the service')
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True, allow_blank=True)
    category = RecentlyActivatedCategorySerializer()
    message = serializers.CharField(help_text="The admin's wording, e.g. \"Diwali is coming up! Add a Diwali Special service to your service list.\"")
    announcedAt = serializers.DateTimeField(
        help_text='When the admin announced it. Remember (subCategoryId, announcedAt) as "already shown": announcing again '
                  'gives a new announcedAt, so a service the artist still has not added is shown again.')


class RecentlyActivatedServicesResponseSerializer(serializers.Serializer):
    data = serializers.ListField(child=RecentlyActivatedServiceSerializer())
