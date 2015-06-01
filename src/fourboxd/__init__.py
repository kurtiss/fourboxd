#!/usr/bin/env python
# encoding: utf-8
"""
__init__.py
Created by Kurtiss Hare
"""

from __future__ import print_function

import foursquare
import functools
import itertools
import json
import letterboxd
import more_itertools
import multiprocessing
import pprint
import re
import slugify
import sys
import threading
import time
import urlparse

import SimpleHTTPServer
import SocketServer

from datetime import datetime


def sync():
	import argparse
	import getpass

	p = argparse.ArgumentParser()
	args = p.parse_args()

	lb_username = raw_input("Letterboxd Username: ")
	lb_password = getpass.getpass(prompt = "Letterboxd Password: ")
	s = login(lb_username, lb_password)
	s.transfer()

def login(*args, **kwargs):
	return Session.login(*args, **kwargs)


class Session(object):
	_DEFAULT_PORT = 8844
	_CLIENT_ID = "NTBIBTP4TNFOHS4Q5215PD1VGBVTXDVBWPO0PZ3V3MXEYFYD"
	_CLIENT_SECRET = "HYNGQXIL3ZX1QCYLFIRT5OKVC3VUDKBXJYSIWRKNNGXVGXH1"
	_OLDEST_FIRST = "oldestfirst"
	_CHECKIN_QUERY_LIMIT = 250
	_LB_LIST_SLUG = "4boxdsync"
	_LB_LIST_ID = "4boxdsync_id"
	_FS_ACCESS_TOKEN = "fs_access_token"
	_FS_TIMESTAMP = "fs_timestamp"
	_FB_ISNEW = "__isnew__"

	@classmethod
	def login(cls, lb_username, lb_password, fs_auth_params = None):
		lb_client = letterboxd.LetterboxdSession(lb_username, lb_password)
		lb_client.signin()
		fb_config = dict()

		try:
			fb_config_list = lb_client.get_list(cls._LB_LIST_SLUG)
		except LookupError:
			lb_list_id = None
		else:
			lb_list_id = fb_config_list["id"]
			try:
				fb_config = json.loads(fb_config_list["notes"])
			except ValueError:
				pass

		fs_access_token = fb_config.setdefault(cls._FS_ACCESS_TOKEN, None)
		fb_config[cls._LB_LIST_ID] = lb_list_id
		fb_config.setdefault(cls._FS_TIMESTAMP, 0)

		if fs_access_token:
			fs_client = foursquare.Foursquare(access_token = fs_access_token)
		else:
			fs_auth_params = fs_auth_params if fs_auth_params else {}
			fs_client = Session.authorize_fs_client(**fs_auth_params)

		return cls(fs_client, lb_client, fb_config)

	@classmethod
	def authorize_fs_client(cls, fs_client_id = _CLIENT_ID, fs_client_secret = _CLIENT_SECRET, server_port = _DEFAULT_PORT):

		fs_client = foursquare.Foursquare(
			client_id = fs_client_id,
			client_secret = fs_client_secret,
			redirect_uri = "http://localhost:{0}/".format(server_port)
		)

		queue = multiprocessing.Queue(maxsize = 1)
		server = ServerThread(queue, server_port)
		server.start()

		try:
			print("Please visit the following URL in your browser and follow the prompts:\r\n\r\n{0}\r\n".format(
				fs_client.oauth.auth_url()
			))
			redirect_code = queue.get()
		finally:
			server.cancel()

		access_token = fs_client.oauth.get_token(redirect_code)
		print("Your access token is:\r\n{0}\r\n".format(access_token))

		fs_client.set_access_token(access_token)

		return fs_client

	def __init__(self, fs_client, lb_client, fb_config):
		self.fs_client = fs_client
		self.lb_client = lb_client
		self.fb_config =  fb_config

	def _checkins(self):
		offset = 0
		len_results = self._CHECKIN_QUERY_LIMIT
		null_event = null_venue = dict(categories = [])
		movie_shout_r = re.compile("^(?P<title>.*)\([^\)]+\)$", re.DOTALL)
		tstamp = self.fb_config[self._FS_TIMESTAMP]

		while len_results == self._CHECKIN_QUERY_LIMIT:
			checkins_response = self.fs_client.users.checkins(params = dict(
				limit = self._CHECKIN_QUERY_LIMIT,
				afterTimestamp = tstamp,
				offset = offset,
				sort = self._OLDEST_FIRST
			))

			checkins = checkins_response["checkins"]["items"]
			len_results = len(checkins)
			offset += len_results

			for checkin in checkins:
				if checkin["createdAt"] > tstamp:
					event = checkin.get("event", null_event)
					venue = checkin.get("venue", null_venue)
					event_is_movie = "Movie" in (c.get("name") for c in event["categories"])
					venue_is_theater = "Movie Theater" in (c.get("name") for c in venue["categories"])
					shout = checkin.get("shout")

					if event_is_movie:
						event_name = event["name"]
					else:
						event_name = None

					movie_shout_m = movie_shout_r.match(shout or "")

					if event_is_movie or (venue_is_theater and shout) or movie_shout_m:
						checkin_dt = datetime.fromtimestamp(checkin["createdAt"])

						if movie_shout_m:
							movie_shout_title = movie_shout_m.groups("title")[0].rstrip()
						else:
							movie_shout_title = None

						if event_name:
							title_guess = event_name
						elif movie_shout_m:
							title_guess = movie_shout_title
						else:
							title_guess = shout

						yield dict(
							title_guess = title_guess,
							event_name = event_name,
							movie_shout_title = movie_shout_title,
							shout = shout,
							venue = venue["name"],
							date = checkin_dt
						)

	def transfer(self):
		try:
			self._do_transfer()
		finally:
			self.sync()

	def _do_transfer(self):
		get_lb_results = lambda t: self.lb_client.search(t, limit = 100)[:9]
		should_continue = True
		checkin_iter = more_itertools.peekable(self._checkins())

		while should_continue and checkin_iter.peek(None) != None:
			checkin = checkin_iter.next()
			title_guess = checkin["title_guess"]
			lb_results = get_lb_results(title_guess)
			should_query = True

			while should_query:
				lb_result = None

				lines = [
					u"Title | {0}".format(title_guess),
					u"Shout | {0}".format(checkin["shout"]),
					u"Venue | {0}".format(checkin["venue"]),
					u" Date | {0}".format(checkin["date"].strftime("%Y-%m-%d"))
				]
				max_line_len = max(len(l) for l in lines)
				print_rule = lambda c: print("+" + c + (c * max_line_len) + c + "+")
				print_line = lambda l: print(u"| {0}{1} |".format(l, u" " * (max_line_len - len(l))))

				print("")
				print_rule("=")
				print_line(lines[0])
				print_rule("=")
				for line in lines[1:]:
					print_line(line)
				print_rule("-")

				if lb_results:
					for number, lb_option in itertools.izip(itertools.count(1), lb_results):
						print(u" {0}) {1}".format(number, lb_option["title"]))
					print(" ...")
				else:
					print(" ** No Letterboxd search results found. **")

				print(" S) Search Letterboxd for another title.")
				print(" E) Enter an exact letterboxd slug.")
				print(" I) Ignore this checkin.")
				print(" R) See raw checkin information.")
				print(" Q) Quit.")
				print("")

				selection = raw_input("> ").lower()

				try:
					index = int(selection) - 1
				except ValueError:
					if selection == "s":
						title_guess = raw_input("Title: ")
						lb_results = get_lb_results(title_guess)
					elif selection == "e":
						slug_guess = raw_input("Slug: ")
						try:
							slug_result = self.lb_client.search_by_slug(slug_guess)
						except LookupError:
							pass
						else:
							if slug_result:
								lb_results = [slug_result]
					elif selection == "i":
						should_query = False
					elif selection == "r":
						pprint.pprint(checkin)
					elif selection == "q":
						should_query = False
						should_continue = False
				else:
					try:
						lb_result = lb_results[index]
					except IndexError:
						lb_result = None
					else:
						self.transfer_checkin(checkin, lb_result)
						should_query = False

			if should_continue:
				self.fb_config[self._FS_TIMESTAMP] = int(time.mktime(checkin["date"].timetuple()))

	def transfer_checkin(self, checkin, film):
		try:
			diary_entry = self.lb_client.get_diary_entry(film["slug"])
		except LookupError:
			self.lb_client.save_diary_entry(
				film["id"],
				date_watched = checkin["date"],
				tags = [slugify.slugify(u"4sq {0}".format(checkin["venue"]))]
			)

		else:
			if diary_entry["date_watched"]:
				print("You've already added this film to Letterboxd. It was marked seen on {0}.".format(
					diary_entry["date_watched"].strftime("%m/%d/%Y")
				))
			else:
				print("You've already added this film to Letterboxd.")


	def sync(self):
		list_id = self.fb_config[self._LB_LIST_ID]

		if list_id is None:
			syncfn = functools.partial(self.lb_client.new_list, self._LB_LIST_SLUG)
		else:
			syncfn = functools.partial(self.lb_client.edit_list, self._LB_LIST_SLUG, list_id)

		self.fb_config[self._FS_ACCESS_TOKEN] = self.fs_client.base_requester.oauth_token
		self.fb_config[self._LB_LIST_ID] = syncfn(notes = json.dumps(self.fb_config))


class ServerHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
	queue = None

	def __init__(self, *args, **kwargs):
		SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

	def do_GET(self):
		params = urlparse.urlparse(self.path)
		query = urlparse.parse_qs(params.query)
		redirect_code = query["code"][0]
		self.queue.put_nowait(redirect_code)

		response = """
			<html>
				<head>
				<title>fourboxd is authenticating...</title>
				<script type="text/javascript">
				window.onload = function() { open(location, "_self").close(); }
				</script>
				</head>
			<body>
			</body>
			</html>
		"""
		self.send_response(200)
		self.send_header("Content-type", "text/html")
		self.send_header("Content-length", len(response))
		self.end_headers()
		self.wfile.write(response)

	def log_message(self, format, *args):
		pass


class ServerThread(threading.Thread):
	def __init__(self, queue, port):
		super(ServerThread, self).__init__()
		self.daemon = True
		self.cancelled = False
		self.queue = queue
		self.port = port

	def cancel(self):
		self.cancelled = True

	def run(self):
		class MyHandler(ServerHandler):
			queue = self.queue

		server = SocketServer.TCPServer(("localhost", self.port), MyHandler)

		while not self.cancelled:
			server.handle_request()

	def update(self):
		pass

