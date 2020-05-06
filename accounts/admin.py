# -*- coding: utf-8 -*-

#
# Freesound is (c) MUSIC TECHNOLOGY GROUP, UNIVERSITAT POMPEU FABRA
#
# Freesound is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Freesound is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     See AUTHORS file.
#

import json

import gearman
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.utils.functional import cached_property
from django.db import connection
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django_object_actions import DjangoObjectActions
from django.contrib.auth.forms import UserChangeForm
from django.forms import ValidationError

from accounts.models import Profile, UserFlag, EmailPreferenceType, OldUsername, EmailBounce


FULL_DELETE_USER_ACTION_NAME = 'full_delete_user'
DELETE_USER_DELETE_SOUNDS_ACTION_NAME = 'delete_user_delete_sounds'
DELETE_USER_KEEP_SOUNDS_ACTION_NAME = 'delete_user_keep_sounds'


def disable_active_user(modeladmin, request, queryset):
    if request.POST.get('confirmation', False):
        gm_client = gearman.GearmanClient(settings.GEARMAN_JOB_SERVERS)
        for user in queryset:
            gm_client.submit_job("delete_user",
                    json.dumps({'user_id':user.id, 'action': DELETE_USER_DELETE_SOUNDS_ACTION_NAME}),
                wait_until_complete=False, background=True)
        messages.add_message(request, messages.INFO, '%d users will be soft deleted asynchronously, related sound are '
                                                     'going to be deleted as well' % (queryset.count()))
        return HttpResponseRedirect(reverse('admin:auth_user_changelist'))

    params = [(k,v) for k in request.POST.keys() for v in request.POST.getlist(k)]
    tvars = {'anonymised': [], 'params': params}
    for obj in queryset:
        info = obj.profile.get_info_before_delete_user(remove_sounds=True)
        model_count = {model._meta.verbose_name_plural: len(objs) for model,
                objs in info['deleted'].model_objs.items()}
        anon = {'anonymised': []}
        anon['model_count'] = dict(model_count).items()
        anon['logic_deleted'] = info['logic_deleted']
        anon['name'] = info['anonymised']
        tvars['anonymised'].append(anon)

    return render(request, 'accounts/delete_confirmation.html', tvars)

disable_active_user.short_description = "'Soft' delete selected users, preserve posts, threads and comments " \
                                        "(delete sounds)"


def disable_active_user_preserve_sounds(modeladmin, request, queryset):
    if request.POST.get('confirmation', False):
        gm_client = gearman.GearmanClient(settings.GEARMAN_JOB_SERVERS)
        for user in queryset:
            gm_client.submit_job("delete_user",
                    json.dumps({'user_id':user.id, 'action': DELETE_USER_KEEP_SOUNDS_ACTION_NAME}),
                wait_until_complete=False, background=True)
        messages.add_message(request, messages.INFO,
                             '%d users will be soft deleted asynchronously' % (queryset.count()))
        return HttpResponseRedirect(reverse('admin:auth_user_changelist'))

    params = [(k,v) for k in request.POST.keys() for v in request.POST.getlist(k)]
    tvars = {'anonymised': [], 'params': params}
    for obj in queryset:
        info = obj.profile.get_info_before_delete_user(remove_sounds=False)
        tvars['anonymised'].append({'name': info['anonymised']})
    return render(request, 'accounts/delete_confirmation.html', tvars)

disable_active_user_preserve_sounds.short_description = "'Soft' delete selected users, preserve sounds and " \
                                                        "everything else"


class ProfileAdmin(admin.ModelAdmin):
    raw_id_fields = ('user', 'geotag')
    list_display = ('user', 'home_page', 'signature', 'is_whitelisted')
    ordering = ('id', )
    list_filter = ('is_whitelisted', )
    search_fields = ('=user__username', )

admin.site.register(Profile, ProfileAdmin)


class UserFlagAdmin(admin.ModelAdmin):
    raw_id_fields = ('user', 'reporting_user', 'content_type')
    list_display = ('user', 'reporting_user', 'content_type')

admin.site.register(UserFlag, UserFlagAdmin)


class LargeTablePaginator(Paginator):
    """ We use the information on postgres table 'reltuples' to avoid using count(*) for performance. """
    @cached_property
    def count(self):
        try:
            if not self.object_list.query.where:
                cursor = connection.cursor()
                cursor.execute("SELECT reltuples FROM pg_class WHERE relname = %s",
                    [self.object_list.query.model._meta.db_table])
                ret = int(cursor.fetchone()[0])
                return ret
            else :
                return self.object_list.count()
        except :
            # AttributeError if object_list has no count() method.
            return len(self.object_list)


class AdminUserForm(UserChangeForm):

    def clean_username(self):
        username = self.cleaned_data["username"]
        # Check that:
        #   1) It is not taken by another user
        #   2) It was not used in the past by another (or the same) user
        # NOTE: as opposed as in accounts.forms.ProfileForm, here we don't impose the limitation of changing the
        # username a maximum number of times.
        try:
            User.objects.exclude(pk=self.instance.id).get(username__iexact=username)
        except User.DoesNotExist:
            try:
                OldUsername.objects.get(username__iexact=username)
            except OldUsername.DoesNotExist:
                return username
        raise ValidationError("This username is already taken or has been in used in the past by this or some other "
                              "user.")


class FreesoundUserAdmin(DjangoObjectActions, UserAdmin):
    search_fields = ('=username', '=email')
    actions = (disable_active_user, disable_active_user_preserve_sounds, )
    list_display = ('username', 'email')
    list_filter = ()
    ordering = ('id', )
    show_full_result_count = False
    form = AdminUserForm
    fieldsets = (
         (None, {'fields': ('username', 'password')}),
         ('Personal info', {'fields': ('email', )}),
         ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups')}),
     ('Important dates', {'fields': ('last_login', 'date_joined')}),
     )

    paginator = LargeTablePaginator

    def full_delete(self, request, obj):
        username = obj.username
        if request.method == "POST":
            gm_client = gearman.GearmanClient(settings.GEARMAN_JOB_SERVERS)
            gm_client.submit_job("delete_user",
                    json.dumps({'user_id': obj.id, 'action': FULL_DELETE_USER_ACTION_NAME}),
                wait_until_complete=False, background=True)
            messages.add_message(request, messages.INFO,
                                 'User \'%s\' will be fully deleted '
                                 'asynchronously from the database' % username)
            return HttpResponseRedirect(reverse('admin:auth_user_changelist'))

        info = obj.profile.get_info_before_delete_user(remove_sounds=False, remove_user=True)
        model_count = {model._meta.verbose_name_plural: len(objs) for model, objs in info['deleted'].model_objs.items()}
        tvars = {'anonymised': []}
        anon = dict()
        anon['model_count'] = dict(model_count).items()
        anon['name'] = info['anonymised']
        anon['deleted'] = True
        tvars['anonymised'].append(anon)
        return render(request, 'accounts/delete_confirmation.html', tvars)
    full_delete.label = "Full delete user"
    full_delete.short_description = 'Completely delete user from db'

    def delete_include_sounds(self, request, obj):
        username = obj.username
        if request.method == "POST":
            gm_client = gearman.GearmanClient(settings.GEARMAN_JOB_SERVERS)
            gm_client.submit_job("delete_user",
                    json.dumps({'user_id': obj.id, 'action': DELETE_USER_DELETE_SOUNDS_ACTION_NAME}),
                wait_until_complete=False, background=True)
            messages.add_message(request, messages.INFO,
                                 'User \'%s\' will be soft deleted'
                                 ' asynchronously. Sounds and other related'
                                 ' content will be deleted.' % username)
            return HttpResponseRedirect(reverse('admin:auth_user_changelist'))
        info = obj.profile.get_info_before_delete_user(remove_sounds=True)
        model_count = {model._meta.verbose_name_plural: len(objs) for model,
                objs in info['deleted'].model_objs.items()}
        tvars = {'anonymised': []}
        anon = {}
        anon['model_count'] = dict(model_count).items()
        anon['logic_deleted'] = info['logic_deleted']
        anon['name'] = info['anonymised']
        tvars['anonymised'].append(anon)
        return render(request, 'accounts/delete_confirmation.html', tvars)

    delete_include_sounds.label = "Soft delete user (delete sounds)"
    delete_include_sounds.short_description = disable_active_user.short_description

    def delete_preserve_sounds(self, request, obj):
        username = obj.username
        if request.method == "POST":
            gm_client = gearman.GearmanClient(settings.GEARMAN_JOB_SERVERS)
            gm_client.submit_job("delete_user",
                    json.dumps({'user_id': obj.id, 'action': DELETE_USER_KEEP_SOUNDS_ACTION_NAME}),
                wait_until_complete=False, background=True)
            messages.add_message(request, messages.INFO,
                                 'User \'%s\' will be soft deleted asynchronously. Comments and other content '
                                 'will appear under anonymised account' % username)
            return HttpResponseRedirect(reverse('admin:auth_user_changelist'))

        info = obj.profile.get_info_before_delete_user(remove_sounds=False)
        tvars = {'anonymised': []}
        tvars['anonymised'].append({'name': info['anonymised']})
        return render(request, 'accounts/delete_confirmation.html', tvars)
    delete_preserve_sounds.label = "Soft delete user (preserve sounds)"
    delete_preserve_sounds.short_description = disable_active_user_preserve_sounds.short_description

    change_actions = ('full_delete', 'delete_include_sounds', 'delete_preserve_sounds', )

admin.site.unregister(User)
admin.site.register(User, FreesoundUserAdmin)


class OldUsernameAdmin(admin.ModelAdmin):
    search_fields = ('=username', )
    raw_id_fields = ('user', )
    list_display = ('user', 'username')

admin.site.register(OldUsername, OldUsernameAdmin)


class EmailBounceAdmin(admin.ModelAdmin):
    search_fields = ('=user__username',)
    list_display = ('user', )

admin.site.register(EmailBounce, EmailBounceAdmin)


admin.site.register(EmailPreferenceType)


