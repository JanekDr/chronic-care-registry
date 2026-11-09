from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    """Standardowe uwierzytelnianie Django z etykietą interfejsu rejestru."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Login"
        self.fields["username"].help_text = "Wpisz login nadany przez administratora."
