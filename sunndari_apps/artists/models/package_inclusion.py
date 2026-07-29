from django.db import models


class PackageInclusion(models.Model):
    inclusion_id = models.AutoField(primary_key=True)
    package = models.ForeignKey(
        'artists.PricingPackage',
        on_delete=models.CASCADE,
        related_name='inclusions',
    )
    inclusion_text = models.CharField(max_length=300)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'package_inclusions'
        ordering = ['order']

    def __str__(self):
        return f"Package #{self.package_id}: {self.inclusion_text}"

    @staticmethod
    def set_for_package(package_id: int, inclusions: list) -> None:
        PackageInclusion.objects.filter(package_id=package_id).delete()
        objs = [
            PackageInclusion(package_id=package_id, inclusion_text=text, order=idx)
            for idx, text in enumerate(inclusions)
        ]
        PackageInclusion.objects.bulk_create(objs)

    @staticmethod
    def get_for_package(package_id: int) -> list:
        return list(
            PackageInclusion.objects.filter(package_id=package_id).values(
                'inclusion_id', 'package_id', 'inclusion_text', 'order',
            )
        )
