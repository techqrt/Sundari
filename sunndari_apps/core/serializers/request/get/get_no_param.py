import dataclasses
from sunndari_apps.common.serializers.request.get import GetSerializer


@dataclasses.dataclass
class NoParamRequest:
    values: str = ''
    user_id: int = None
    present_url: str = None


class NoParamSerializer(GetSerializer):
    def create(self, validated_data) -> NoParamRequest:
        return NoParamRequest(values=validated_data.get('values', ''))
