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

import mock
from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core import mail
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from accounts.forms import FsPasswordResetForm, DeleteUserForm, UsernameField
from accounts.models import Profile, SameUser, ResetEmailRequest, OldUsername
from comments.models import Comment
from forum.models import Thread, Post, Forum
from sounds.models import License, Sound, Pack, DeletedSound
from utils.mail import transform_unique_email


class UserRegistrationAndActivation(TestCase):
    fixtures = ['users']

    def test_user_save(self):
        u = User.objects.create_user("testuser2", password="testpass")
        self.assertEqual(Profile.objects.filter(user=u).exists(), True)
        u.save()  # Check saving user again (with existing profile) does not fail

    @override_settings(RECAPTCHA_PUBLIC_KEY='')
    def test_user_registration(self):
        username = 'new_user'

        # Try registration without accepting tos
        resp = self.client.post(reverse('accounts-register'), data={
            u'username': [username],
            u'password1': [u'123456'],
            u'accepted_tos': [u''],
            u'email1': [u'example@email.com'],
            u'email2': [u'example@email.com']
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('You must accept the terms of use', resp.content)
        self.assertEqual(User.objects.filter(username=username).count(), 0)
        self.assertEqual(len(mail.outbox), 0)  # No email sent

        # Try registration with bad email
        resp = self.client.post(reverse('accounts-register'), data={
            u'username': [username],
            u'password1': [u'123456'],
            u'accepted_tos': [u'on'],
            u'email1': [u'exampleemail.com'],
            u'email2': [u'exampleemail.com']
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Enter a valid email', resp.content)
        self.assertEqual(User.objects.filter(username=username).count(), 0)
        self.assertEqual(len(mail.outbox), 0)  # No email sent

        # Try registration with no username
        resp = self.client.post(reverse('accounts-register'), data={
            u'username': [''],
            u'password1': [u'123456'],
            u'accepted_tos': [u'on'],
            u'email1': [u'example@email.com'],
            u'email2': [u'example@email.com']
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('This field is required', resp.content)
        self.assertEqual(User.objects.filter(username=username).count(), 0)
        self.assertEqual(len(mail.outbox), 0)  # No email sent

        # Try registration with different email addresses
        resp = self.client.post(reverse('accounts-register'), data={
            u'username': [''],
            u'password1': [u'123456'],
            u'accepted_tos': [u'on'],
            u'email1': [u'example@email.com'],
            u'email2': [u'exampl@email.net']
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Please confirm that your email address is the same', resp.content)
        self.assertEqual(User.objects.filter(username=username).count(), 0)
        self.assertEqual(len(mail.outbox), 0)  # No email sent

        # Try successful registration
        resp = self.client.post(reverse('accounts-register'), data={
            u'username': [username],
            u'password1': [u'123456'],
            u'accepted_tos': [u'on'],
            u'email1': [u'example@email.com'],
            u'email2': [u'example@email.com']
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Registration done, activate your account', resp.content)
        self.assertEqual(User.objects.filter(username=username).count(), 1)
        self.assertEqual(len(mail.outbox), 1)  # An email was sent!
        self.assertTrue(settings.EMAIL_SUBJECT_PREFIX in mail.outbox[0].subject)
        self.assertTrue(settings.EMAIL_SUBJECT_ACTIVATION_LINK in mail.outbox[0].subject)

        # Try register again with same username
        resp = self.client.post(reverse('accounts-register'), data={
            u'username': [username],
            u'password1': [u'123456'],
            u'accepted_tos': [u'on'],
            u'email1': [u'example@email.com'],
            u'email2': [u'example@email.com']
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('You cannot use this username to create an account', resp.content)
        self.assertEqual(User.objects.filter(username=username).count(), 1)
        self.assertEqual(len(mail.outbox), 1)  # No new email sent

        # Try with repeated email address
        resp = self.client.post(reverse('accounts-register'), data={
            u'username': ['a_different_username'],
            u'password1': [u'123456'],
            u'accepted_tos': [u'on'],
            u'email1': [u'example@email.com'],
            u'email2': [u'example@email.com']
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('You cannot use this email address to create an account', resp.content)
        self.assertEqual(User.objects.filter(username=username).count(), 1)
        self.assertEqual(len(mail.outbox), 1)  # No new email sent

    def test_user_activation(self):
        user = User.objects.get(username="User6Inactive")  # Inactive user in fixture

        # Test calling accounts-activate with wrong hash, user should not be activated
        bad_hash = '4dad3dft'
        resp = self.client.get(reverse('accounts-activate', args=[user.username, bad_hash]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['decode_error'], True)
        self.assertEqual(User.objects.get(username="User6Inactive").is_active, False)

        # Test calling accounts-activate with good hash, user should be activated
        from utils.encryption import create_hash
        good_hash = create_hash(user.id)
        resp = self.client.get(reverse('accounts-activate', args=[user.username, good_hash]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['all_ok'], True)
        self.assertEqual(User.objects.get(username="User6Inactive").is_active, True)

        # Test calling accounts-activate for a user that does not exist
        resp = self.client.get(reverse('accounts-activate', args=["noone", hash]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['user_does_not_exist'], True)


class UserDelete(TestCase):
    fixtures = ['licenses', 'sounds']

    def create_user_and_content(self, is_index_dirty=True):
        user = User.objects.create_user("testuser", password="testpass")
        # Create comments
        target_sound = Sound.objects.all()[0]
        for i in range(0, 3):
            target_sound.add_comment(user, "Comment %i" % i)
        # Create threads and posts
        thread = Thread.objects.create(author=user, title="Test thread", forum=Forum.objects.create(name="Test forum"))
        for i in range(0, 3):
            Post.objects.create(author=user, thread=thread, body="Post %i body" % i)
        # Create sounds and packs
        pack = Pack.objects.create(user=user, name="Test pack")
        for i in range(0, 3):
            Sound.objects.create(user=user,
                                 original_filename="Test sound %i" % i,
                                 pack=pack,
                                 is_index_dirty=is_index_dirty,
                                 license=License.objects.all()[0],
                                 md5="fakemd5%i" % i,
                                 moderation_state="OK",
                                 processing_state="OK")
        return user

    def test_user_delete_make_invalid_password(self):
        user = self.create_user_and_content(is_index_dirty=False)
        user.profile.delete_user()
        self.assertFalse(user.has_usable_password())

    def test_user_delete_keep_sounds(self):
        # This should set user's attribute active to false and anonymize it
        user = self.create_user_and_content(is_index_dirty=False)
        user.profile.delete_user()
        self.assertEqual(User.objects.get(id=user.id).profile.is_deleted_user, True)

        self.assertEqual(user.username, "deleted_user_%s" % user.id)
        self.assertEqual(user.profile.about, '')
        self.assertEqual(user.profile.home_page, '')
        self.assertEqual(user.profile.signature, '')
        self.assertEqual(user.profile.geotag, None)

        self.assertEqual(Comment.objects.filter(user__id=user.id).exists(), True)
        self.assertEqual(Thread.objects.filter(author__id=user.id).exists(), True)
        self.assertEqual(Post.objects.filter(author__id=user.id).exists(), True)
        self.assertEqual(DeletedSound.objects.filter(user__id=user.id).exists(), False)
        self.assertEqual(Pack.objects.filter(user__id=user.id).exists(), True)
        self.assertEqual(Sound.objects.filter(user__id=user.id).exists(), True)
        self.assertEqual(Sound.objects.filter(user__id=user.id)[0].is_index_dirty, True)

    @mock.patch('sounds.models.delete_sound_from_solr')
    def test_user_delete_remove_sounds(self, delete_sound_solr):
        # This should set user's attribute deleted_user to True and anonymize it,
        # also should remove users Sounds and Packs, and create DeletedSound
        # objects
        user = self.create_user_and_content()
        user_sounds = Sound.objects.filter(user=user)
        user_sound_ids = [s.id for s in user_sounds]
        user.profile.delete_user(remove_sounds=True)
        self.assertEqual(User.objects.get(id=user.id).profile.is_deleted_user, True)
        self.assertEqual(user.username, "deleted_user_%s" % user.id)
        self.assertEqual(user.profile.about, '')
        self.assertEqual(user.profile.home_page, '')
        self.assertEqual(user.profile.signature, '')
        self.assertEqual(user.profile.geotag, None)

        self.assertEqual(Comment.objects.filter(user__id=user.id).exists(), True)
        self.assertEqual(Thread.objects.filter(author__id=user.id).exists(), True)
        self.assertEqual(Post.objects.filter(author__id=user.id).exists(), True)
        self.assertEqual(Pack.objects.filter(user__id=user.id).exists(), True)
        self.assertEqual(Pack.objects.filter(user__id=user.id).all()[0].is_deleted, True)
        self.assertEqual(Sound.objects.filter(user__id=user.id).exists(), False)
        self.assertEqual(DeletedSound.objects.filter(user__id=user.id).exists(), True)

        calls = [mock.call(i) for i in user_sound_ids]
        delete_sound_solr.assert_has_calls(calls, any_order=True)

    def test_user_delete_using_form(self):
        # This should set user's attribute active to false and anonymize it
        user = self.create_user_and_content(is_index_dirty=False)
        a = self.client.login(username=user.username, password='testpass')
        form = DeleteUserForm(user_id=user.id)
        encr_link = form.initial['encrypted_link']
        resp = self.client.post(reverse('accounts-delete'),
                                {'encrypted_link': encr_link, 'password': 'testpass', 'delete_sounds': 'delete_sounds'})

        self.assertEqual(User.objects.get(id=user.id).profile.is_deleted_user, True)

    def test_fail_user_delete_using_form(self):
        # This should try to delete the account but with a wrong password
        user = self.create_user_and_content(is_index_dirty=False)
        a = self.client.login(username=user.username, password='testpass')
        form = DeleteUserForm(user_id=user.id)
        encr_link = form.initial['encrypted_link']
        resp = self.client.post(reverse('accounts-delete'),
                                {'encrypted_link': encr_link, 'password': 'wrong_pass',
                                 'delete_sounds': 'delete_sounds'})

        self.assertEqual(User.objects.get(id=user.id).profile.is_deleted_user, False)


class UserEmailsUniqueTestCase(TestCase):

    def setUp(self):
        self.user_a = User.objects.create_user("user_a", password="12345", email='a@b.com')
        self.original_shared_email = 'c@d.com'
        self.user_b = User.objects.create_user("user_b", password="12345", email=self.original_shared_email)
        self.user_c = User.objects.create_user("user_c", password="12345",
                                               email=transform_unique_email(self.original_shared_email))
        SameUser.objects.create(
            main_user=self.user_b,
            main_orig_email=self.user_b.email,
            secondary_user=self.user_c,
            secondary_orig_email=self.user_b.email,  # Must be same email (original)
        )
        # User a never had problems with email
        # User b and c had the same email, but user_c's was automaitcally changed to avoid duplicates

    def test_redirects_when_shared_emails(self):
        # Try to log-in with user and go to messages page (any login_required page would work)
        # User a is not in same users table, so redirect should be plain and simple to messages
        # NOTE: in the following tests we don't use `self.client.login` because what we want to test
        # is in fact in the login view logic.
        resp = self.client.post(reverse('login'),
                                {'username': self.user_a, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('messages'))

        resp = self.client.get(reverse('logout'))
        # Now try with user_b and user_c. User b had a shared email with user_c. Even if user_b's email was
        # not changed, he is still redirected to the duplicate email cleanup page
        resp = self.client.post(reverse('login'),
                                {'username': self.user_b, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('accounts-multi-email-cleanup') + '?next=%s' % reverse('messages'))
        resp = self.client.get(reverse('logout'))
        resp = self.client.post(reverse('login'),
                                {'username': self.user_c, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('accounts-multi-email-cleanup') + '?next=%s' % reverse('messages'))

    def test_fix_email_issues_with_secondary_user_email_change(self):
        # user_c changes his email and tries to login, redirect should go to email cleanup page and from there
        # directly to messages (2 redirect steps)
        self.user_c.email = 'new@email.com'  # Must be different than transform_unique_email('c@d.com')
        self.user_c.save()
        resp = self.client.post(reverse('login'), follow=True,
                                data={'username': self.user_c, 'password': '12345', 'next': reverse('messages')})
        self.assertEqual(resp.redirect_chain[0][0],
                          reverse('accounts-multi-email-cleanup') + '?next=%s' % reverse('messages'))
        self.assertEqual(resp.redirect_chain[1][0], reverse('messages'))

        # Also check that related SameUser objects have been removed
        self.assertEqual(SameUser.objects.all().count(), 0)

        resp = self.client.get(reverse('logout'))
        # Now next time user_c tries to go to messages again, there is only one redirect (like for user_a)
        resp = self.client.post(reverse('login'),
                                {'username': self.user_c, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('messages'))

        resp = self.client.get(reverse('logout'))
        # Also if user_b logs in, redirect goes straight to messages
        resp = self.client.post(reverse('login'),
                                {'username': self.user_b, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('messages'))

    def test_fix_email_issues_with_main_user_email_change(self):
        # user_b changes his email and tries to login, redirect should go to email cleanup page and from there
        # directly to messages (2 redirect steps). Also user_c email should be changed to the original email of
        # both users
        self.user_b.email = 'new@email.com'  # Must be different than transform_unique_email('c@d.com')
        self.user_b.save()
        resp = self.client.post(reverse('login'), follow=True,
                                data={'username': self.user_b, 'password': '12345', 'next': reverse('messages')})
        self.assertEqual(resp.redirect_chain[0][0],
                          reverse('accounts-multi-email-cleanup') + '?next=%s' % reverse('messages'))
        self.assertEqual(resp.redirect_chain[1][0], reverse('messages'))

        # Check that user_c email was changed
        self.user_c = User.objects.get(id=self.user_c.id)  # Reload user from db
        self.assertEqual(self.user_c.email, self.original_shared_email)

        # Also check that related SameUser objects have been removed
        self.assertEqual(SameUser.objects.all().count(), 0)

        resp = self.client.get(reverse('logout'))
        # Now next time user_b tries to go to messages again, there is only one redirect (like for user_a)
        resp = self.client.post(reverse('login'),
                                {'username': self.user_b, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('messages'))

        resp = self.client.get(reverse('logout'))
        # Also if user_c logs in, redirect goes straight to messages
        resp = self.client.post(reverse('login'),
                                {'username': self.user_c, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('messages'))

    def test_fix_email_issues_with_both_users_email_change(self):
        # If both users have changed email, we should make sure that user_c email is not overwritten before
        # SameUser object is deleted
        self.user_b.email = 'new@email.com'
        self.user_b.save()
        self.user_c.email = 'new2w@email.com'
        self.user_c.save()
        resp = self.client.post(reverse('login'), follow=True,
                                data={'username': self.user_b, 'password': '12345', 'next': reverse('messages')})
        self.assertEqual(resp.redirect_chain[0][0],
                          reverse('accounts-multi-email-cleanup') + '?next=%s' % reverse('messages'))
        self.assertEqual(resp.redirect_chain[1][0], reverse('messages'))

        # Check that user_c email was not changed
        self.user_c = User.objects.get(id=self.user_c.id)  # Reload user from db
        self.assertEqual(self.user_c.email, 'new2w@email.com')

        # Also check that related SameUser objects have been removed
        self.assertEqual(SameUser.objects.all().count(), 0)

        resp = self.client.get(reverse('logout'))
        # Now next time user_b tries to go to messages again, there is only one redirect (like for user_a)
        resp = self.client.post(reverse('login'),
                                {'username': self.user_b, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('messages'))

        resp = self.client.get(reverse('logout'))
        # Also if user_c logs in, redirect goes straight to messages
        resp = self.client.post(reverse('login'),
                                {'username': self.user_c, 'password': '12345', 'next': reverse('messages')})
        self.assertRedirects(resp, reverse('messages'))

    def test_user_profile_get_email(self):
        # Here we test that when we send an email to users that have SameUser objects we chose the right email address

        # user_a has no SameUser objects, emails should be sent directly to his address
        self.assertEqual(self.user_a.profile.get_email_for_delivery(), self.user_a.email)

        # user_b has SameUser with user_c, but user_b is main user so emails should be sent directly to his address
        self.assertEqual(self.user_b.profile.get_email_for_delivery(), self.user_b.email)

        # user_c should get emails at user_b email address (user_b is main user)
        self.assertEqual(self.user_c.profile.get_email_for_delivery(), self.user_b.email)

        # If we remove SameUser entries, email of user_c is sent directly to his address
        SameUser.objects.all().delete()
        self.assertEqual(self.user_c.profile.get_email_for_delivery(), self.user_c.email)


class PasswordReset(TestCase):
    def test_reset_form_get_users(self):
        """Check that a user with an unknown password hash can reset their password"""

        user = User.objects.create_user("testuser", email="testuser@freesound.org")

        # Using Django's password reset form, no user will be returned
        form = PasswordResetForm()
        dj_users = form.get_users("testuser@freesound.org")
        self.assertEqual(len(list(dj_users)), 0)

        # But using our form, a user will be returned
        form = FsPasswordResetForm()
        fs_users = form.get_users("testuser@freesound.org")
        self.assertEqual(list(fs_users)[0].get_username(), user.get_username())

    @override_settings(SITE_ID=2)
    def test_reset_view_with_email(self):
        """Check that the reset password view calls our form"""
        Site.objects.create(id=2, domain="freesound.org", name="Freesound")
        user = User.objects.create_user("testuser", email="testuser@freesound.org")
        self.client.post(reverse("password_reset"), {"email_or_username": "testuser@freesound.org"})

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Password reset on Freesound")

    @override_settings(SITE_ID=2)
    def test_reset_view_with_username(self):
        """Check that the reset password view calls our form"""
        Site.objects.create(id=2, domain="freesound.org", name="Freesound")
        user = User.objects.create_user("testuser", email="testuser@freesound.org")
        self.client.post(reverse("password_reset"), {"email_or_username": "testuser"})

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Password reset on Freesound")

    @override_settings(SITE_ID=2)
    def test_reset_view_with_long_username(self):
        """Check that the reset password fails with long username"""
        Site.objects.create(id=2, domain="freesound.org", name="Freesound")
        user = User.objects.create_user("testuser", email="testuser@freesound.org")
        long_mail = ('1' * 255) + '@freesound.org'
        resp = self.client.post(reverse("password_reset"), {"email_or_username": long_mail})

        self.assertNotEqual(resp.context['form'].errors, None)


class EmailResetTestCase(TestCase):
    def test_reset_email_form(self):
        """ Check that reset email with the right parameters """
        user = User.objects.create_user("testuser", email="testuser@freesound.org")
        user.set_password('12345')
        user.save()
        a = self.client.login(username=user.username, password='12345')
        resp = self.client.post(reverse('accounts-email-reset'), {
            'email': u'new_email@freesound.org',
            'password': '12345',
        })
        self.assertRedirects(resp, reverse('accounts-email-reset-done'))
        self.assertEqual(ResetEmailRequest.objects.filter(user=user, email="new_email@freesound.org").count(), 1)

    def test_reset_email_form_existing_email(self):
        """ Check that reset email with an existing email address """
        user = User.objects.create_user("new_user", email="new_email@freesound.org")
        user = User.objects.create_user("testuser", email="testuser@freesound.org")
        user.set_password('12345')
        user.save()
        a = self.client.login(username=user.username, password='12345')
        resp = self.client.post(reverse('accounts-email-reset'), {
            'email': u'new_email@freesound.org',
            'password': '12345',
        })
        self.assertRedirects(resp, reverse('accounts-email-reset-done'))
        self.assertEqual(ResetEmailRequest.objects.filter(user=user, email="new_email@freesound.org").count(), 0)

    def test_reset_long_email(self):
        """ Check reset email with a long email address """
        long_mail = ('1' * 255) + '@freesound.org'
        user = User.objects.create_user("testuser", email="testuser@freesound.org")
        user.set_password('12345')
        user.save()
        a = self.client.login(username=user.username, password='12345')
        resp = self.client.post(reverse('accounts-email-reset'), {
            'email': long_mail,
            'password': '12345',
        })

        self.assertNotEqual(resp.context['form'].errors, None)


class ReSendActivationTestCase(TestCase):
    def test_resend_activation_code_from_email(self):
        """
        Check that resend activation code doesn't return an error with post request (use email to identify user)
        """
        user = User.objects.create_user("testuser", email="testuser@freesound.org", is_active=False)
        resp = self.client.post(reverse('accounts-resend-activation'), {
            'user': u'testuser@freesound.org',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)  # Check email was sent
        self.assertTrue(settings.EMAIL_SUBJECT_PREFIX in mail.outbox[0].subject)
        self.assertTrue(settings.EMAIL_SUBJECT_ACTIVATION_LINK in mail.outbox[0].subject)

        resp = self.client.post(reverse('accounts-resend-activation'), {
            'user': u'new_email@freesound.org',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)  # Check no new email was sent (len() is same as before)

    def test_resend_activation_code_from_username(self):
        """
        Check that resend activation code doesn't return an error with post request (use username to identify user)
        """
        user = User.objects.create_user("testuser", email="testuser@freesound.org", is_active=False)
        resp = self.client.post(reverse('accounts-resend-activation'), {
            'user': u'testuser',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)  # Check email was sent
        self.assertTrue(settings.EMAIL_SUBJECT_PREFIX in mail.outbox[0].subject)
        self.assertTrue(settings.EMAIL_SUBJECT_ACTIVATION_LINK in mail.outbox[0].subject)

        resp = self.client.post(reverse('accounts-resend-activation'), {
            'user': u'testuser_does_not_exist',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)  # Check no new email was sent (len() is same as before)

    def test_resend_activation_code_from_long_username(self):
        """
        Check that resend activation code returns an error if username is too long
        """
        long_mail = ('1' * 255) + '@freesound.org'
        resp = self.client.post(reverse('accounts-resend-activation'), {
            'user': long_mail,
        })
        self.assertNotEqual(resp.context['form'].errors, None)
        self.assertEqual(len(mail.outbox), 0)  # Check email wasn't sent


class UsernameReminderTestCase(TestCase):
    def test_username_reminder(self):
        """ Check that send username reminder doesn't return an error with post request """
        user = User.objects.create_user("testuser", email="testuser@freesound.org")
        resp = self.client.post(reverse('accounts-username-reminder'), {
            'user': u'testuser@freesound.org',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)  # Check email was sent
        self.assertTrue(settings.EMAIL_SUBJECT_PREFIX in mail.outbox[0].subject)
        self.assertTrue(settings.EMAIL_SUBJECT_USERNAME_REMINDER in mail.outbox[0].subject)

        resp = self.client.post(reverse('accounts-username-reminder'), {
            'user': u'new_email@freesound.org',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)  # Check no new email was sent (len() is same as before)

    def test_username_reminder_length(self):
        """ Check that send long username reminder return an error with post request """
        long_mail = ('1' * 255) + '@freesound.org'
        user = User.objects.create_user("testuser", email="testuser@freesound.org")
        resp = self.client.post(reverse('accounts-username-reminder'), {
            'user': long_mail,
        })
        self.assertNotEqual(resp.context['form'].errors, None)
        self.assertEqual(len(mail.outbox), 0)


class ChangeUsernameTest(TestCase):

    def test_change_username_creates_old_username(self):
        # Create user and check no OldUsername objects exist
        userA = User.objects.create_user('userA', email='userA@freesound.org')
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 0)

        # Change username and check a OldUsername is created
        userA.username = 'userANewUsername'
        userA.save()
        self.assertEqual(OldUsername.objects.filter(username='userA', user=userA).count(), 1)

        # Save again user and check no new OldUsername are created
        userA.save()
        self.assertEqual(OldUsername.objects.filter(username='userA', user=userA).count(), 1)

        # Change username again and check a new OldUsername has been created
        userA.username = 'userANewNewUsername'
        userA.save()
        self.assertEqual(OldUsername.objects.filter(username='userANewUsername', user=userA).count(), 1)
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 2)

        # Change username back to the previous one (won't be allowed in admin or profile form) and check that a new
        # OldUsername object has been created for the last username
        userA.username = "userANewUsername"
        userA.save()
        self.assertEqual(OldUsername.objects.filter(username='userANewNewUsername', user=userA).count(), 1)
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 3)

        # Change again the username to another previosuly used username and check that no new OldUsername is created
        userA.username = 'userA'
        userA.save()
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 3)

    @override_settings(USERNAME_CHANGE_MAX_TIMES=2)
    def test_change_username_form_profile_page(self):
        # Create user and login
        userA = User.objects.create_user('userA', email='userA@freesound.org', password='testpass')
        self.client.login(username='userA', password='testpass')

        # Test save profile without changing username
        resp = self.client.post(reverse('accounts-edit'), data={u'profile-username': [u'userA']})
        self.assertRedirects(resp, reverse('accounts-home'))  # Successful edit redirects to home
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 0)

        # Now rename user for the first time
        resp = self.client.post(reverse('accounts-edit'), data={u'profile-username': [u'userANewName']})
        self.assertRedirects(resp, reverse('accounts-home'))  # Successful edit redirects to home
        self.assertEqual(OldUsername.objects.filter(username='userA', user=userA).count(), 1)

        # Now rename user for the second time
        resp = self.client.post(reverse('accounts-edit'), data={u'profile-username': [u'userANewNewName']})
        self.assertRedirects(resp, reverse('accounts-home'))  # Successful edit redirects to home
        self.assertEqual(OldUsername.objects.filter(username='userANewName', user=userA).count(), 1)
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 2)

        # Try rename user with an existing username from another user
        userB = User.objects.create_user('userB', email='userB@freesound.org')
        resp = self.client.post(reverse('accounts-edit'), data={u'profile-username': [userB.username]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['profile_form'].has_error('username'), True)  # Error in username field
        userA.refresh_from_db()
        self.assertEqual(userA.username, 'userANewNewName')  # Username has not changed
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 2)

        # Try rename user with a username that was already used by the same user in the past
        resp = self.client.post(reverse('accounts-edit'), data={u'profile-username': [u'userA']})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['profile_form'].has_error('username'), True)  # Error in username field
        userA.refresh_from_db()
        self.assertEqual(userA.username, 'userANewNewName')  # Username has not changed
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 2)

        # Try to rename for a third time to a valid username but can't rename anymore because exceeded maximum
        # USERNAME_CHANGE_MAX_TIMES (which is set to 2 for this test)
        resp = self.client.post(reverse('accounts-edit'), data={u'profile-username': [u'userANewNewNewName']})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['profile_form'].has_error('username'), True)  # Error in username field
        userA.refresh_from_db()
        self.assertEqual(userA.username, 'userANewNewName')  # Username has not changed
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 2)

    @override_settings(USERNAME_CHANGE_MAX_TIMES=2)
    def test_change_username_form_admin(self):
        User.objects.create_user('superuser', password='testpass', is_superuser=True, is_staff=True)
        self.client.login(username='superuser', password='testpass')

        # Create user and get admin change url
        userA = User.objects.create_user('userA', email='userA@freesound.org', password='testpass')
        admin_change_url = reverse('admin:auth_user_change', args=[userA.id])

        post_data = {'username': u'userA',
                     'email': userA.email,  # Required to avoid breaking unique constraint with empty email
                     'date_joined_0': "2015-10-06", 'date_joined_1': "16:42:00"}  # date_joined required

        # Test save user without changing username
        resp = self.client.post(admin_change_url, data=post_data)
        self.assertRedirects(resp, reverse('admin:auth_user_changelist'))  # Successful edit redirects to users list
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 0)

        # Now rename user for the first time
        post_data.update({'username': u'userANewName'})
        resp = self.client.post(admin_change_url, data=post_data)
        self.assertRedirects(resp, reverse('admin:auth_user_changelist'))  # Successful edit redirects to users list
        self.assertEqual(OldUsername.objects.filter(username='userA', user=userA).count(), 1)

        # Now rename user for the second time
        post_data.update({'username': u'userANewNewName'})
        resp = self.client.post(admin_change_url, data=post_data)
        self.assertRedirects(resp, reverse('admin:auth_user_changelist'))  # Successful edit redirects to users list
        self.assertEqual(OldUsername.objects.filter(username='userANewName', user=userA).count(), 1)
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 2)

        # Try rename user with an existing username from another user
        userB = User.objects.create_user('userB', email='userB@freesound.org')
        post_data.update({'username': userB.username})
        resp = self.client.post(admin_change_url, data=post_data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(bool(resp.context['adminform'].errors), True)  # Error in username field
        userA.refresh_from_db()
        self.assertEqual(userA.username, 'userANewNewName')  # Username has not changed
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 2)

        # Try rename user with a username that was already used by the same user in the past
        post_data.update({'username': u'userA'})
        resp = self.client.post(admin_change_url, data=post_data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(bool(resp.context['adminform'].errors), True)  # Error in username field
        userA.refresh_from_db()
        self.assertEqual(userA.username, 'userANewNewName')  # Username has not changed
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 2)

        # Try to rename for a third time to a valid username. Because we are in admin now, the USERNAME_CHANGE_MAX_TIMES
        # restriction does not apply so rename should work correctly
        post_data.update({'username': u'userANewNewNewName'})
        resp = self.client.post(admin_change_url, data=post_data)
        self.assertRedirects(resp, reverse('admin:auth_user_changelist'))  # Successful edit redirects to users list
        self.assertEqual(OldUsername.objects.filter(username='userANewNewName', user=userA).count(), 1)
        self.assertEqual(OldUsername.objects.filter(user=userA).count(), 3)

    def test_change_username_case_insensitiveness(self):
        """Test that changing the username for a new version of the username with different capitalization does not
        create a new OldUsername object.
        """
        # Create user and login
        userA = User.objects.create_user('userA', email='userA@freesound.org', password='testpass')
        self.client.login(username='userA', password='testpass')

        # Rename "userA" to "UserA", should not create OldUsername object
        resp = self.client.post(reverse('accounts-edit'), data={u'profile-username': [u'UserA']})
        self.assertRedirects(resp, reverse('accounts-home'))
        self.assertEqual(OldUsername.objects.filter(username='userA', user=userA).count(), 0)


class UsernameValidatorTest(TestCase):
    """ Makes sure that username validation works as intended """

    class TestForm(forms.Form):
        username = UsernameField()

    def test_valid(self):
        """ Alphanumerics, _, - and + are ok"""
        form = self.TestForm(data={'username': 'normal_user.name+'})
        self.assertTrue(form.is_valid())

    def test_email_like_invalid(self):
        """ We don't allow @ character """
        form = self.TestForm(data={'username': 'email@username'})
        self.assertFalse(form.is_valid())

    def test_short_invalid(self):
        """ Should be longer than 3 characters """
        form = self.TestForm(data={'username': 'a'})
        self.assertFalse(form.is_valid())

    def test_long_invalid(self):
        """ Should be shorter than 30 characters """
        form = self.TestForm(data={'username': 'a' * 31})
        self.assertFalse(form.is_valid())
