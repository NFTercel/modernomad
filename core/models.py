from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.contrib.sites.models import Site
from django.core import urlresolvers

# imports for signals
import django.dispatch 
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save

from django.core.mail import send_mail
from confirmation_email import confirmation_email_details



class House(models.Model):
	# meta
	created = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)
	admins = models.ManyToManyField(User, blank=True, null=True)
	# location
	address = models.CharField(max_length=400, unique=True)
	latLong = models.CharField(max_length=100, unique=True)
	# community size
	residents = models.IntegerField() 
	rooms = models.IntegerField() 
	# descriptive
	name = models.CharField(max_length=200) # required
	picture = models.ImageField(upload_to="photos/%Y/%m/%d", blank=True, null=True)
	description = models.TextField(max_length=2000, null=True, blank=True) # + suggested max length. possible things to incl. are description of mission/values, house rules etc. if desired. 
	mission_values = models.TextField(max_length=2000, null=True, blank=True) # comma separated list of tags
	amenities = models.TextField(blank=True, null=True)
	guests = models.NullBooleanField(blank=True, null=True)
	events = models.NullBooleanField(blank=True, null=True)
	events_description = models.TextField(blank=True, null=True)
	space_share = models.NullBooleanField(blank=True, null=True)
	space_share_description = models.TextField(blank=True, null=True)
	slug = models.CharField(max_length=100, unique=True, blank=True, null=True)
	contact_ok = models.NullBooleanField(blank=True, null=True)
	contact = models.EmailField(blank=True, null=True) # required if contact_ok = True
	# social
	website = models.URLField(verify_exists = True, null=True, blank=True, unique=True)
	twitter_handle = models.CharField(max_length=100, null=True, blank=True)
	pictures_feed = models.CharField(max_length=400, null=True, blank=True)

	# future - mailing lists?
	# deprecated: 
	# get_in_touch = models.CharField(max_length=100, unique=True, blank=True, null=True) --> replace with "ok to contact?" + email addy
	# house_rules = models.TextField(blank=True, null=True) 

	def __unicode__(self):
		if self.name:
			return (self.name)
		else:
			return self.address

RESOURCE_TYPES = (
	('private', 'private'),
	('hostel', 'hostel'),
	('conference_room', 'conference room'),
)

class Resource(models.Model):
	house = models.ForeignKey(House)
	name = models.CharField(max_length=200)
	description = models.TextField()
	resource_type = models.CharField(max_length=200, choices=RESOURCE_TYPES)
	def __unicode__(self):
		return (self.name)


class Reservation(models.Model):
	PENDING = 'pending'
	APPROVED = 'approved'
	CONFIRMED = 'confirmed'
	DECLINED = 'declined'
	DELETED = 'deleted'

	PRIVATE = 'private'
	SHARED = 'shared'
	PREFER_SHARED = 'prefer_shared'
	PREFER_PRIVATE = 'prefer_private'

	RESERVATION_STATUSES = (
		(PENDING, 'pending'),
		(APPROVED, 'approved'),
		(CONFIRMED, 'confirmed'),
		(DECLINED, 'declined'),
		(DELETED, 'deleted'),
	)

	ACCOMMODATION_PREFERENCES = (
		(PRIVATE, 'Private'),
		(SHARED, 'Shared'),
		(PREFER_SHARED, 'Prefer shared but will take either'),
		(PREFER_PRIVATE, 'Prefer private but will take either')
	)

	created = models.DateTimeField(auto_now_add=True)
	updated = models.DateTimeField(auto_now=True)
	status = models.CharField(max_length=200, choices=RESERVATION_STATUSES, default=PENDING)
	user = models.ForeignKey(User)
	arrive = models.DateField(verbose_name='Arrival Date')
	depart = models.DateField(verbose_name='Departure Date')
	arrival_time = models.CharField(help_text='Optional, if known', max_length=200, blank=True, null=True)
	accommodation_preference = models.CharField(verbose_name='Accommodation Type Preference', max_length=200, choices = ACCOMMODATION_PREFERENCES)
	tags = models.CharField(max_length =200, help_text='What are 2 or 3 tags that characterize this trip?')
	projects = models.TextField(verbose_name='Current Projects', help_text='Describe one or more projects you are currently working on')
	sharing = models.TextField(help_text="Is there anything you'd be interested in learning or sharing while you are here?")
	discussion = models.TextField(help_text="We like discussing thorny issues with each other. What's a question that's been on your mind lately that you don't know the answer to?")
	purpose = models.TextField(verbose_name='What are you in town for?')
	referral = models.CharField(max_length=200, verbose_name='How did you hear about us?')
	comments = models.TextField(blank=True, null=True, verbose_name='Any additional comments')

	@models.permalink
	def get_absolute_url(self):
		return ('core.views.ReservationDetail', [str(self.id)])

	def __unicode__(self):
		return "reservation %d" % self.id

# send house_admins notification of new reservation
@receiver(post_save, sender=Reservation)
def notify_house_admins(sender, instance, **kwargs):
	if kwargs['created'] == True:
		obj = Reservation.objects.get(pk=instance.pk)
		house_admins = User.objects.filter(groups__name='house_admin')

		subject = "[Embassy SF] Reservation Request, %s %s, %s - %s" % (obj.user.first_name, 
			obj.user.last_name, str(obj.arrive), str(obj.depart))
		sender = "stay@embassynetwork.com"
		domain = Site.objects.get_current().domain
		admin_path = urlresolvers.reverse('admin:core_reservation_change', args=(obj.id,))
		message = '''Howdy, 

A new reservation request has been submitted.

You can view, approve or deny this request at %s%s.
		''' % (domain, admin_path)
		# XXX TODO this is terrible. should have an alias and let a mail agent handle this!
		for admin in house_admins:
			recipient = [admin.email,]
			send_mail(subject, message, sender, recipient)


# define a signal for reservation approval
reservation_approved = django.dispatch.Signal(providing_args=["url", "reservation"])

@receiver(pre_save, sender=Reservation)
def detect_changes(sender, instance, **kwargs):
	try:
		obj = Reservation.objects.get(pk=instance.pk)
	except Reservation.DoesNotExist:
		pass
	else:
		if obj.status == Reservation.PENDING and instance.status == Reservation.APPROVED:
			reservation_approved.send(sender=Reservation, url=instance.get_absolute_url, reservation = instance)
		# if the status was changed from anything else to 'confirmed', generate an email
		elif obj.status != Reservation.CONFIRMED and instance.status == Reservation.CONFIRMED:
			subject = "[Embassy SF] Reservation Confirmation, %s - %s" % (str(instance.arrive), 
			str(instance.depart))
			sender = "stay@embassynetwork.com"
			domain = 'http://' + Site.objects.get_current().domain
			# XXX change this to reservation.house.get_absolute_url()
			house_info_url = domain + '/guestinfo/'
			reservation_url = domain + instance.get_absolute_url()
			recipient = [instance.user.email,]
			text = '''Dear %s,

This email confirms we will see you from %s - %s. Information on accessing the
house, house norms, and transportation can be viewed online at %s, and for
your convenience is also included below. View or edit your reservation at 
%s. 

Let us know if you have any questions.
Thanks and see you soon!

-------------------------------------------------------------------------------

''' % (instance.user.first_name.title(), instance.arrive, instance.depart, house_info_url, reservation_url)
			text += confirmation_email_details

			send_mail(subject, text, sender, recipient) 

			pass

# XXX do we even need a second signal?
@receiver(reservation_approved, sender=Reservation)
def approval_notify(sender, url, reservation, **kwargs):
	recipient = [reservation.user.email]
	subject = "[Embassy SF] Reservation Approval"
	domain = Site.objects.get_current().domain
	message = "Your reservation request for %s - %s has been approved. You must confirm this reservation to finalize!\n\nView your reservation details and confirm at %s%s" % (
		str(reservation.arrive), str(reservation.depart), domain, reservation.get_absolute_url())
	sender = "stay@embassynetwork.com"
	send_mail(subject, message, sender, recipient)


class UserProfile(models.Model):
	# User model fields: username, first_name, last_name, email, 
	# password, is_staff, is_active, is_superuser, last_login, date_joined,
	user = models.OneToOneField(User)
	updated = models.DateTimeField(auto_now=True)
	image = models.ImageField(upload_to="data/avatars/%Y/%m/%d/", blank=True)
	bio = models.TextField("About you", blank=True, null=True)
	links = models.TextField(help_text="Comma-separated", blank=True, null=True)

	def __unicode__(self):
		return (self.user.__unicode__())

# ??
User.profile = property(lambda u: UserProfile.objects.get_or_create(user=u)[0])

