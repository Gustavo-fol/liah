from django import forms
from django.core.exceptions import ValidationError

from nucleo.models import Categoria, ConfiguracaoIA, ContextoReferencia, RegraDicionario


class ConfiguracaoIAForm(forms.ModelForm):
    """
    As chaves NUNCA voltam para a tela: o campo vem sempre vazio.
    Deixar vazio = manter a chave atual. Preencher = trocar.
    """
    nova_chave_principal = forms.CharField(
        label="Chave de API da IA principal", required=False, strip=True,
        widget=forms.PasswordInput(attrs={"autocomplete": "off", "placeholder": "deixe vazio para manter a atual"}),
    )
    nova_chave_secundaria = forms.CharField(
        label="Chave de API da IA secundária", required=False, strip=True,
        widget=forms.PasswordInput(attrs={"autocomplete": "off", "placeholder": "deixe vazio para manter a atual"}),
    )
    apagar_chave_principal = forms.BooleanField(label="Apagar a chave principal", required=False)
    apagar_chave_secundaria = forms.BooleanField(label="Apagar a chave secundária", required=False)

    class Meta:
        model = ConfiguracaoIA
        fields = ("ativa", "provedor_principal", "modelo_principal", "provedor_secundario", "modelo_secundario")
        help_texts = {
            "modelo_principal": "Ex.: gpt-4o-mini. Use o botão Testar para ver os modelos da sua conta.",
            "modelo_secundario": "Ex.: gemini-3.5-flash. Use o botão Testar para ver os modelos da sua conta.",
            "ativa": "Desligado: a Liah responde só com as regras fixas (útil em emergência ou sem crédito).",
        }

    def save(self, usuario, commit=True):
        cfg = super().save(commit=False)
        for qual in ("principal", "secundaria"):
            if self.cleaned_data.get(f"apagar_chave_{qual}"):
                cfg.definir_chave(qual, "")
            elif self.cleaned_data.get(f"nova_chave_{qual}"):
                cfg.definir_chave(qual, self.cleaned_data[f"nova_chave_{qual}"])
        cfg.atualizada_por = usuario
        if commit:
            cfg.save()
        return cfg


class RegraForm(forms.ModelForm):
    class Meta:
        model = RegraDicionario
        fields = (
            "titulo", "categoria", "sinais", "exemplos", "nivel_risco", "orientacao", "encaminhamento",
            "status", "revisado_por_psicologo", "observacoes_psicologo",
        )
        widgets = {
            "sinais": forms.Textarea(attrs={"rows": 3}),
            "exemplos": forms.Textarea(attrs={"rows": 4}),
            "orientacao": forms.Textarea(attrs={"rows": 3}),
            "observacoes_psicologo": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        dados = super().clean()
        # Regra de ouro: só vira "aprovada" depois da revisão do psicólogo.
        if dados.get("status") == RegraDicionario.Status.APROVADA and not dados.get("revisado_por_psicologo"):
            raise ValidationError("Para aprovar, marque que a regra foi revisada pelo psicólogo.")
        return dados


class ContextoForm(forms.ModelForm):
    class Meta:
        model = ContextoReferencia
        fields = ("titulo", "fonte", "conteudo", "aprovado")
        widgets = {"conteudo": forms.Textarea(attrs={"rows": 12})}


class SugerirRegrasForm(forms.Form):
    categoria = forms.ChoiceField(label="Categoria", choices=Categoria.choices)
    quantidade = forms.IntegerField(label="Quantas regras", min_value=1, max_value=5, initial=3)
