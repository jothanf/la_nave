# Generated by Django 5.1.4 on 2024-12-22 01:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nave', '0003_remove_shelfmodel_position_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='producttypemodel',
            name='codigo',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
