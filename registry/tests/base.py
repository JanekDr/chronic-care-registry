from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils.crypto import get_random_string


class RoleTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = get_random_string(32)
        users = get_user_model()
        cls.personel_group = Group.objects.create(name="personel")
        cls.personel = users.objects.create_user("personel", password=cls.password)
        cls.personel.groups.add(cls.personel_group)
        cls.outsider = users.objects.create_user("bez-roli", password=cls.password)
        cls.staff_outsider = users.objects.create_user(
            "staff-bez-roli", password=cls.password, is_staff=True,
        )
        cls.administrator = users.objects.create_superuser(
            "administrator", password=cls.password,
        )
