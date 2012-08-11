### Python wrapper for VinAudit API
# Takes a VIN number and returns "NULL" or JSON with the data


# http://www.vinaudit.com/api-documentation

DEBUG = True

import json, urllib, urllib2, time, datetime, sys
from mongoengine import *

USERNAME = 'gstech'
PASSWORD = 'zpnr5974'
API_KEY = 'QX86F96ZNM6KGSW'

connect('vinhistory', host="mongodb://jdotjdot:virginia@ds035617.mongolab.com:35617/garafa")

def MAIN_URL(_type):
	'''This function takes one of the following:
	'query', 'order', 'generate', 'report'
	'''

	return "https://api.vinaudit.com/%s.php" % _type

def get_page(url, **data):
	data['pass'] = data['password']
	del data['password']
	return urllib2.urlopen(url, data).read()

def Query(vin):
	'''
	vin, key, format, skipspec, mode, callback
	'''

	results = json.loads(
		get_page(MAIN_URL('query'), vin=vin, key=API_KEY, format=json)
		)

	if results['success']:
		return results['id']
	else:
		# If unsuccessful, add more error catching
		return False

def Order(vin, _id):
	'''
	id, user, pass, vin, key, format, mode, callback
	'''

	results = json.loads(
		get_page(MAIN_URL('query'), 
				 id=_id,
				 user=USERNAME,
				 password=PASSWORD, #change to 'pass'
				 vin=vin,
				 key=API_KEY,
				 format='json'
				 )
		)

	if results['success']:
		return True
	elif results['error'] == 'no_balance':
		raise NoBalanceError, "You have no balance remaining."
	elif results['error'] == 'charge_failed':
		raise ChargeFailedError, "Your financial credentials are invalid."


def Generate(_id):
	'''
	id, key, format
	'''

	results = json.loads(
		get_page(MAIN_URL('generate'),
			id = _id,
			key = API_KEY,
			format = 'json'
			)
		)

	if results['success']:
		return True
	else:
		if results['error'] == 'not_ready':
			#Recursively 
			time.sleep(1)
			Generate(_id)
		elif results['error'] == 'nmvtis_unavailable':
			raise Exception, "NMVTIS unavailable, try again later"
		elif results['error'] == 'failed':
			raise Exception, "Unexpected error"


def Report(_id):

	'''
	id, format
	'''
	
	results = json.loads(
		get_page(MAIN_URL('report'), 
			id = _id,
			format = 'json'
			)
		)

	if DEBUG: print(results)
	return results

def GetCarInformation(vin):
	
	order_id = Query(vin)
	if order_id:
		try_order = Order(vin, order_id)
		if try_order:
			try_generate = Generate(_id)
			if try_generate:
				results = Report(order_id)

	# upload the results to mongodb
	newcar = Car(vin = vin,
				 id = order_id,
				 datetime_pulled = datetime.datetime.now(),
				 **results
				 )
	newcar.save()

class NoBalanceError(Exception):
	pass

class ChargeFailedError(Exception):
	pass

################################
### Mongoengine Data
################################

class Car(DynamicDocument):
	vin = StringField(max_length=50, required=True)
	id = StringField(max_length = 50)
	datetime_pulled = DateTimeField()

if __name__ == '__main__':

	# command line: vinaudit.py <VIN> <VIN> ...

	if len(sys.argv) > 1:
		for _input in sys.argv[1:]:
			GetCarInformation(_input)
