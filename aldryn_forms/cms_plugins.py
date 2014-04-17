# -*- coding: utf-8 -*-
from django import forms
from django.conf import settings
from django.contrib.admin import TabularInline
from django.core.validators import MinLengthValidator
from django.utils.translation import ugettext_lazy as _

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from captcha.fields import ReCaptchaField

from aldryn_forms import models
from .forms import (
    FormPluginForm,
    TextFieldForm,
    BooleanFieldForm,
    MultipleSelectFieldForm,
    SelectFieldForm,
    CaptchaFieldForm
)
from .validators import MinChoicesValidator, MaxChoicesValidator
from .views import SendView


class FormElement(CMSPluginBase):
    # Don't cache anything.
    cache = False
    module = _('Forms')

    def get_form_fields(self, instance):
        raise NotImplementedError()


class FieldContainer(FormElement):

    allow_children = True

    def get_form_fields(self, instance):
        form_fields = {}
        for child_plugin_instance in instance.child_plugin_instances:
            child_plugin = child_plugin_instance.get_plugin_instance()[1]
            if hasattr(child_plugin, 'get_form_fields'):
                fields = child_plugin.get_form_fields(instance=child_plugin_instance)
                form_fields.update(fields)
        return form_fields


class FormPlugin(FieldContainer):

    render_template = 'aldryn_forms/form.html'
    name = _('Form')
    model = models.FormPlugin
    form = FormPluginForm
    filter_horizontal = ['recipients']

    fieldsets = [
        (
            'General options',
            {'fields': ['name', 'error_message', 'recipients']}
        ),
        (
            'Redirect',
            {'fields': ['redirect_type', 'page', 'url']}
        )
    ]

    def render(self, context, instance, placeholder):
        context = super(FormPlugin, self).render(context, instance, placeholder)
        if 'form' not in context:  # the context not from form processing view
            template_response = SendView.as_view(
                template_name=self.render_template
            )(request=context['request'], pk=instance.pk)
            context.update(template_response.context_data)
        return context

    def get_form_class(self, instance):
        """
        Constructs form class basing on children plugin instances.
        """
        fields = self.get_form_fields(instance)
        return forms.forms.DeclarativeFieldsMetaclass('AldrynDynamicForm', (forms.Form,), fields)

    def get_success_url(self, instance):
        if instance.redirect_type == models.FormPlugin.REDIRECT_TO_PAGE:
            return instance.page.get_absolute_url()
        elif instance.redirect_type == models.FormPlugin.REDIRECT_TO_URL:
            return instance.url
        else:
            raise RuntimeError('Form is not configured properly.')

plugin_pool.register_plugin(FormPlugin)


class Fieldset(FieldContainer):

    render_template = 'aldryn_forms/fieldset.html'
    name = _('Fieldset')
    model = models.FieldsetPlugin

plugin_pool.register_plugin(Fieldset)


class Field(FormElement):

    render_template = 'aldryn_forms/field.html'
    model = models.FieldPlugin

    def get_field_name(self, instance):
        return u'aldryn-forms-field-%d' % (instance.pk,)

    def get_form_fields(self, instance):
        return {self.get_field_name(instance=instance): self.get_form_field(instance=instance)}

    def get_form_field(self, instance):
        raise NotImplementedError()

    def render(self, context, instance, placeholder):
        context = super(Field, self).render(context, instance, placeholder)
        if 'form' in context:
            context['field'] = context['form'][self.get_field_name(instance=instance)]
        return context

    def get_fieldsets(self, request, obj=None):
        if self.form:
            fields = set(self.form._meta.fields)
        else:
            fields = ['label']

        in_fields = lambda x: x in fields

        general_fields = filter(in_fields, ['label', 'placeholder_text', 'help_text'])
        fieldsets = [
            (_('General options'), {'fields': general_fields}),
        ]

        boundries_fields = filter(in_fields, ['min_value', 'max_value'])
        if boundries_fields:
            fieldsets.append(
                (_('Min and max values'), {'fields': boundries_fields}))

        required_fields = filter(in_fields, ['required', 'required_message'])
        if required_fields:
            fieldsets.append(
                (_('Required'), {'fields': required_fields}))

        return fieldsets

    def get_error_messages(self, instance):
        if instance.required_message:
            return {'required': instance.required_message}
        else:
            return None


class TextField(Field):

    name = _('Text Field')
    form = TextFieldForm

    def get_form_field(self, instance):
        validators = []
        if instance.min_value:
            validators.append(MinLengthValidator(instance.min_value))
        field = forms.CharField(
            max_length=instance.max_value,
            label=instance.label,
            help_text=instance.help_text,
            required=instance.required,
            error_messages=self.get_error_messages(instance=instance),
            validators=validators)
        if instance.placeholder_text:
            field.widget.attrs['placeholder'] = instance.placeholder_text
        return field

plugin_pool.register_plugin(TextField)


class BooleanField(Field):

    name = _('Yes/No Field')
    form = BooleanFieldForm

    def get_form_field(self, instance):
        field = forms.BooleanField(
            label=instance.label,
            help_text=instance.help_text,
            error_messages=self.get_error_messages(instance=instance),
            required=instance.required)
        return field

plugin_pool.register_plugin(BooleanField)


class SelectOptionInline(TabularInline):

    model = models.Option


class SelectField(Field):

    name = _('Select Field')
    form = SelectFieldForm
    inlines = [SelectOptionInline]

    def get_form_field(self, instance):
        field = forms.ModelChoiceField(
            queryset=instance.option_set.all(),
            label=instance.label,
            help_text=instance.help_text,
            error_messages=self.get_error_messages(instance=instance),
            required=instance.required)
        return field

plugin_pool.register_plugin(SelectField)


class MultipleSelectField(SelectField):

    name = _('Multiple Select Field')
    form = MultipleSelectFieldForm

    def get_form_field(self, instance):
        validators = []
        if instance.min_value:
            validators.append(MinChoicesValidator(limit_value=instance.min_value))
        if instance.max_value:
            validators.append(MaxChoicesValidator(limit_value=instance.min_value))
        field = forms.ModelMultipleChoiceField(
            queryset=instance.option_set.all(),
            label=instance.label,
            help_text=instance.help_text,
            required=instance.min_value,
            widget=forms.CheckboxSelectMultiple,
            validators=validators)
        return field

plugin_pool.register_plugin(MultipleSelectField)


class CaptchaField(Field):

    name = _('Captcha Field')
    form = CaptchaFieldForm

    def get_form_field(self, instance):
        field = ReCaptchaField(
            label=instance.label,
            error_messages=self.get_error_messages(instance=instance))
        return field

if getattr(settings, 'RECAPTCHA_PUBLIC_KEY', None) and getattr(settings, 'RECAPTCHA_PRIVATE_KEY', None):
    plugin_pool.register_plugin(CaptchaField)


class SubmitButton(FormElement):

    render_template = 'aldryn_forms/submit_button.html'
    name = _('Submit Button')
    model = models.ButtonPlugin

    def get_form_fields(self, instance):
        return {}

plugin_pool.register_plugin(SubmitButton)
