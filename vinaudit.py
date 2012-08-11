### Python wrapper for VinAudit API
# Takes a VIN number or report and returns "NULL" or JSON with the data

# To add:
#	(1) Concurrency, so that calling the program with
#		multiple VINs and/or report IDs allows for asynchornous
#		data pulling.

# http://www.vinaudit.com/api-documentation

import json, urllib, urllib2, time, datetime, sys, argparse
from mongoengine import *

USERNAME = 'gstech'
PASSWORD = 'zpnr5974'
API_KEY = 'QX86F96ZNM6KGSW'

connect('vinhistory', host="mongodb://JJ:2berlin@ds035617.mongolab.com:35617/garafa")

def MAIN_URL(_type):
	'''This function takes one of the following:
	'query', 'order', 'generate', 'report'
	'''

	return "https://api.vinaudit.com/%s.php" % _type

def get_page(url, **data):
	if DEBUG: print data
	if 'password' in data:
		data['pass'] = data['password']
		del data['password']
	text = urllib2.urlopen(url, urllib.urlencode(data)).read()

	return text

def Query(vin):
	'''
	vin, key, format, skipspec, mode, callback
	'''

	if DEBUG: print "Query"

	results = json.loads(
		get_page(MAIN_URL('query'), vin=vin, key=API_KEY, format='json')
		)

	if results['success']:
		return results['id']
	else:
		# If unsuccessful, add more error catching
		if results['error'] == 'invalid_vin':
			raise InvalidVINError, "Invalid VIN provided."
		elif results['error'] == 'fail_nmvtis':
			raise FailNMVTISError, "Failed to reach NMVTIS."
		elif results['error'] == 'no_records':
			print "No record exists in NMVTIS for VIN %s" % vin

		return False

def Order(vin, _id):
	'''
	id, user, pass, vin, key, format, mode, callback
	'''

	if DEBUG: print "Order"

	results = json.loads(
		get_page(MAIN_URL('order'), 
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

	if DEBUG: print "Generate"

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
	
	if DEBUG: print "Report"

	results = json.loads(
		get_page(MAIN_URL('report'), 
			id = _id,
			format = 'json'
			)
		)

	if DEBUG: print(results)
	return results

def GetCarInformation(vin=None, report_id=None):

	if not (vin or report_id):
		raise Exception, "Must supply at least one vin or report_id."
	
	# If ordering the report for the first time:
	if not report_id:
		order_id = Query(vin)
	# to prevent duplicate orders, if we already have the order id:
	else:
		order_id = report_id

	if order_id:
		try_order = Order(vin, order_id)
		if try_order:
			try_generate = Generate(order_id)
			if try_generate:
				results = Report(order_id)

	try:
		results['vinaudit_id'] = results['id']
		del results['id']
	# If results was never defined (b/c 1+ functions failed)
	except UnboundLocalError:
		return


	# upload the results to mongodb
	newcar = Car(#vin = vin,
				 #id = order_id,
				 datetime_pulled = datetime.datetime.now(),
				 **results
				 )

	newcar.save()

class NoBalanceError(Exception):
	pass

class ChargeFailedError(Exception):
	pass

class InvalidVINError(Exception):
	pass

class FailNMVTISError(Exception):
	pass

class NoRecordsError(Exception):
	pass

################################
### Mongoengine Data
################################

class Car(DynamicDocument):
	meta = {'collection': 'vinhistory'}

	vin = StringField(max_length=50, required=True)
	vinaudit_id = StringField(max_length = 50)
	datetime_pulled = DateTimeField()



if __name__ == '__main__': 

	parser = argparse.ArgumentParser()

	parser.add_argument('VINs', action="store", nargs='*', 
		help="List of VINs to report.")
	parser.add_argument('--reports', '-r', action="store", 
		nargs="*", dest="reports",
		help="List of already purchased reports to get.")
	parser.add_argument('--debug', '-d', action="store_true",
		dest="debug",
		default=False, help="Turns on debug option.")

	all_input = parser.parse_args()

	DEBUG = all_input.debug

	if all_input.VINs:
		for _input in all_input.VINs:
			GetCarInformation(_input)
	if all_input.reports:
		for _input in all_input.reports:
			GetCarInformation(report_id = _input)