### Python wrapper for VinAudit API
# Takes a VIN number or report and returns "NULL" or JSON with the data

# To add:
#	(1) Concurrency, so that calling the program with
#		multiple VINs and/or report IDs allows for asynchornous
#		data pulling.
#   (2) Add database to store VINs that haven't worked for whatever reason,
#		especially those that are invalid VINs or aren't available in
#		the database.

# http://www.vinaudit.com/api-documentation

import json, urllib, urllib2, time, datetime, sys, argparse, pprint
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
			if all_input.not_async:
				print "No record exists in NMVTIS for VIN %s" % vin
			else:
				raise NoRecordsError, "No record exists in NMVTIS for VIN %s" % vin

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
	parser.add_argument('--not_asynchronously', '-na', action='store_true',
		default=False, dest="not_async",
		help="Turns off asynchronous evaluation for multiple arguments.")
	parser.add_argument('--reports', '-r', action="store", 
		nargs="*", dest="reports",
		help="List of already purchased reports to get.")
	parser.add_argument('--debug', '-d', action="store_true",
		dest="debug",
		default=False, help="Turns on debug option.")

	all_input = parser.parse_args()

	DEBUG = all_input.debug

	if all_input.not_async:
		if all_input.VINs:
			for _input in all_input.VINs:
				GetCarInformation(_input)
		if all_input.reports:
			for _input in all_input.reports:
				GetCarInformation(report_id = _input)

	#################################################
	### ASYNCHRONOUS CODE
	#################################################

	else:
		import collections
		from twisted.internet import reactor, defer, threads
		from twisted.python import failure

		vin_count = 0 # Probably deprecated; remove this
		balance_ok = True
		run_items = {'vins': [], 'reports': []}
		error_items = collections.defaultdict(list)

		def callprint(ignore, x):
			print x

		def addrunitem(ignore, idnum, report=False):
			if report:
				run_items['reports'].append(idnum)
			else:
				run_items['vins'].append(idnum)

		def adderroritem(ignore, idnum, category):
			error_items[category].append(idnum)

		def end(ignore):
			print "\n\n-------------PROGRAM SUMMARY-------------n"
			print "\nThe following items were successfully run:\n"
			if run_items['vins']:
				print "VINs:\n"
				pprint.pprint(run_items['vins'], indent=2, depth=2)
			if run_items['reports']:
				print "Reports:\n"
				pprint.pprint(run_items['reports'], indent=2, depth=2)

			print "\n\nThe following items were NOT run:\n"

			for item in error_items:
				print item + ":\n"
				pprint.pprint(error_items[item], indent=2, depth=2)

			reactor.stop()

		def handle_various_errors(failure, vin_or_report, _id):

			# Do I actually need vin_or_report?

			if failure.check(NoBalanceError):
				balance_ok = False
				print "No balance remaining: no more VINs will be run."
				error_items['not_attempted'].append(_id)

			elif failure.check(InvalidVINError):
				print _id + " is an invalid " + vin_or_report
				error_items['invalid_vin'].append(_id)

			elif failure.check(FailNMVTISError):
				print _id + " was not run, NMVTIS was not available."
				error_items['fail_nmvtis'].append(_id)

			elif failure.check(NoRecordsError):
				print _id + " did not exist in the NMVTIS database."
				error_items['no_record'].append(_id)

			else:
				failure.raiseException()


		def deferred_GetCarInformation(vin=None, report_id=None):

			# Maybe should rewrite much of this function to not have
			#  to have all of these "vin if vin else report_id", etc.

			if vin and report_id:
				raise Exception, "Shouldn't supply both arguments"

			if vin and balance_ok:
				d = threads.deferToThread(GetCarInformation,
										  vin = vin)
			elif report_id:
				d = threads.deferToThread(GetCarInformation,
										  report_id = report_id)

			# I'm not sure this will actually ever come up,
			#  since the DeferredList is set up before any of the VIN functions
			#  is actually executed, so `balance_ok` will always remain True
			elif vin and not balance_ok:
				d.addCallback(adderroritem, vin, 'not_attempted')
				return d

			d.addCallback(callprint, "Ran for %s %s" % ('VIN' if vin else 'report ID',
														vin if vin else report_id)
						 )

			# Adds the id to the list of successfully run items
			d.addCallback(addrunitem, vin if vin else report_id, True if report_id else False)

			d.addErrback(handle_various_errors, 'VIN' if vin else 'report ID',
												    vin if vin else report_id)

			return d

		dl=[]
		if all_input.VINs:
			dl.extend([deferred_GetCarInformation(vin=x) for x in all_input.VINs])
		if all_input.reports:
			dl.extend([deferred_GetCarInformation(report_id=x) for x in all_input.reports])
		dl = defer.DeferredList(dl)
		dl.addCallback(end)
		reactor.run()