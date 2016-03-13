#!/usr/bin/env python
# encoding: utf-8
"""
letterboxd.py
Created by Kurtiss Hare
"""

import bs4
import datetime
import json
import re
import requests
import time


class LetterboxdSession(object):
	ROOT = "http://letterboxd.com"
	_DIARY_DATE_RE = re.compile(
		"/(?P<username>[^/]+)/films/diary/year/(?P<year>\d+)/(?P<month>\d+)/(?P<day>\d+)/",
		re.DOTALL
	)

	@classmethod
	def url(cls, path):
		return cls.ROOT + path

	def __init__(self, username, password):
		self.http = requests.Session()
		self.username = username
		self.password = password

	def _get_form_csrf(self, url, form_id):
		r = self.http.get(url)
		s = bs4.BeautifulSoup(r.text)
		form = s.find("form", id = form_id)
		return form.find("input", attrs = dict(name = "__csrf"))["value"]

	def _get_signin_csrf(self):
		r = self.http.post(self.url("/ajax/letterboxd-metadata/"))
		j = json.loads(r.text)
		return j["csrf"]

	def signin(self):
		r = self.http.post(self.url("/user/login.do"), data = dict(
			__csrf = self._get_signin_csrf(),
			username = self.username,
			password = self.password
		))
		return r.status_code == 200

	def get_list(self, slug):
		r = self.http.get(self.url("/" + self.username + "/list/" + slug + "/edit/"))
		if r.status_code == 404:
			raise LookupError()

		s = bs4.BeautifulSoup(r.text)

		return dict(
			id = int(s.find("input", id="film-list-editor-id")["value"]),
			notes = s.find("textarea", class_ = "notes-field").text
		)

	def new_list(self, slug, tags = tuple(), notes = "", share_on_facebook = False):
		return self._save_list(
			self._get_form_csrf(self.url("/list/new/"), "list-form"), slug, "", tags,
			notes, share_on_facebook
		)["listId"]

	def edit_list(self, slug, list_id, tags = tuple(), notes = "", share_on_facebook = False):
		return self._save_list(
			self._get_form_csrf(self.url("/{0}/list/{1}/edit/".format(self.username, slug)), "list-form"),
			slug, list_id, tags, notes, share_on_facebook
		)["listId"]

	def _save_list(self, csrf, slug, list_id, tags, notes, share_on_facebook = False):
		data = dict(
			__csrf = csrf,
			filmListId = list_id,
			name = slug,
			tags = "",
			notes = notes,
			shareOnFacebook = "true" if share_on_facebook else "false"
		)

		if tags:
			data.update(dict(
				tag = tags
			))

		r = self.http.post(self.url("/s/save-list"), data = data)
		return json.loads(r.text)

	def search(self, title, limit = 100):
		r = self.http.get(self.url("/s/autocompletefilm"), params = dict(
			q = title.lower(),
			limit = limit,
			timestamp = int(time.time() * 1000)
		))
		j = json.loads(r.text)

		results = []

		for film in j["data"]:
			directors = u"/".join(u" ".join(d["name"].split(" ")[1:]) for d in film["directors"])
			release_year = unicode(film["releaseYear"] or "")
			paren_inner = u", ".join(filter(None, [directors, release_year]))

			if paren_inner:
				paren_outer = u" ({0})".format(paren_inner)
			else:
				paren_outer = u""

			results.append(dict(
				id = film["id"],
				title = u"{0}{1}".format(film["name"], paren_outer),
				slug = filter(None, film["url"].split("/"))[1]
			))

		return results

	def search_by_slug(self, slug):
		r = self.http.get(self.url("/ajax/poster/film/{0}/no-menu/unlinked/70x105/list-item".format(slug)))

		if r.status_code == 404:
			raise LookupError()

		s = bs4.BeautifulSoup(r.text)
		data = s.find("li")

		return dict(
			id = int(data["data-film-id"]),
			title = unicode(data["data-film-name"]),
			slug = slug
		)

	def get_diary_entry(self, slug):
		r = self.http.get(self.url("/{0}/film/{1}".format(self.username, slug)))
		if r.status_code == 404:
			raise LookupError()

		s = bs4.BeautifulSoup(r.text)

		date_link = s.find("a", href = self._DIARY_DATE_RE)
		if date_link:
			date_match = self._DIARY_DATE_RE.match(date_link["href"])
			date_watched = datetime.datetime(
				year = int(date_match.group("year")),
				month = int(date_match.group("month")),
				day = int(date_match.group("day"))
			)
		else:
			date_watched = None

		rating = int(s.find("meta", itemprop = "ratingValue")["content"])
		description = getattr(s.find("div", itemprop = "description"), "content", None)
		tag_links = s.find("ul", class_ = "tags")
		tag_links = tag_links.find_all("a") if tag_links else []
		tags = [tl.text for tl in tag_links]

		return dict(
			date_watched = date_watched,
			rating = rating,
			description = description,
			tags = tags
		)

	def save_diary_entry(self, film_id,
			date_watched = None,
			rating = None,
			review = None,
			tags = None,
			liked = False,
			rewatch = False,
			contains_spoilers = False,
			share_on_facebook = False):
		specified_date = "false" if date_watched is None else "true"
		rewatch = "true" if rewatch else "false"
		share_on_facebook = "true" if share_on_facebook else "false"

		try:
			rating = int(rating)
		except TypeError:
			rating = "0"
		else:
			rating = str(rating)

		try:
			date_watched = date_watched.strftime("%Y-%m-%d")
		except AttributeError:
			date_watched = ""

		tag = [] if tags is None else tags
		if len(tag) == 1:
			sde_tags = tag[0]
		else:
			sde_tags = ""
		liked = 1 if liked else 0
		contains_spoilers = "true" if contains_spoilers else "false"

		r = self.http.post(self.url("/s/save-diary-entry"), data = dict(
			__csrf = self._get_signin_csrf(),
			viewingId = "",
			filmId = film_id,
			specifiedDate = specified_date,
			rewatch = rewatch,
			viewingDateStr =date_watched,
			review = review,
			tags = sde_tags,
			tag = tag,
			liked = liked,
			containsSpoilers = contains_spoilers,
			rating = rating,
			shareOnFacebook = share_on_facebook
		))

		r.raise_for_status()
		return r.json()["viewingId"]
