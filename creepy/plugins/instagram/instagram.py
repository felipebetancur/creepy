#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import logging
import urllib
from urlparse import urlparse, parse_qs
from configobj import ConfigObj

import pytz
from PyQt4.QtGui import QLabel, QLineEdit, QWizard, QWizardPage, QVBoxLayout, QMessageBox, QTextEdit
from instagram.client import InstagramAPI
from models.InputPlugin import InputPlugin
from utilities import GeneralUtilities
# set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(os.path.join(GeneralUtilities.getLogDir(), 'creepy_main.log'))
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(levelname)s:%(asctime)s  In %(filename)s:%(lineno)d: %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


class Instagram(InputPlugin):
    name = "instagram"
    hasWizard = True

    def __init__(self):
        # Try and read the labels file
        labels_config = self.getConfigObj(self.name + '.labels')
        try:
            logger.debug("Trying to load the labels file for the  " + self.name + " plugin .")
            self.labels = labels_config['labels']
        except Exception, err:
            self.labels = None
            logger.error("Could not load the labels file for the  " + self.name + " plugin .")
            logger.exception(err)
        self.config, self.options_string = self.readConfiguration("string_options")
        self.api = None

    def getAuthenticatedAPI(self):
        return InstagramAPI(access_token=self.options_string['hidden_access_token'])

    def isConfigured(self):
        if self.api is None:
            self.api = self.getAuthenticatedAPI()
        try:
            self.api.user()
            return True, ""
        except Exception, err:
            return False, err.error_message

    def searchForTargets(self, search_term):
        logger.debug("Attempting to search for targets. Search term was : " + search_term)
        possibleTargets = []
        try:
            if self.api is None:
                self.api = self.getAuthenticatedAPI()
            results = self.api.user_search(q=search_term)

            for i in results:
                target = {'pluginName': 'Instagram Plugin'}
                target['targetUserid'] = i.id
                target['targetUsername'] = i.username
                target['targetPicture'] = 'profile_pic_%s' % i.id
                target['targetFullname'] = i.full_name
                # save the pic in the temp folder to show it later
                filename = 'profile_pic_%s' % i.id
                temp_file = os.path.join(os.getcwdu(), "temp", filename)
                if not os.path.exists(temp_file):
                    urllib.urlretrieve(i.profile_picture, temp_file)
                possibleTargets.append(target)
            logger.debug(str(len(possibleTargets)) + " possible targets were found matching the search query")
        except Exception, err:
            logger.error("Error searching for targets with instagram plugin.")
            logger.error(err)
        return possibleTargets

    def getAllPhotos(self, uid, count, max_id, photos):
        logger.debug("Attempting to retrieve all photos for user " + uid)
        if self.api is None:
            self.api = self.getAuthenticatedAPI()
        new_photos, next1 = self.api.user_recent_media(user_id=uid, count=count, max_id=max_id)
        if new_photos:
            logger.debug("found " + str(len(new_photos)) + " photos")
            photos.extend(new_photos)
            logger.debug("we now have " + str(len(photos)) + " photos")
        if not next1:
            logger.debug("finished, got all photos")
            return photos
        else:
            a = parse_qs(urlparse(next1).query)
            logger.debug("found more , max_id will now be " + a['max_id'][0])
            return self.getAllPhotos(uid, count, a['max_id'][0], photos)

    def returnAnalysis(self, target, search_params):
        logger.debug("Attempting to retrieve all photos for user " + target['targetUserid'])
        locations_list = []
        try:
            if self.api is None:
                self.api = self.getAuthenticatedAPI()
            photos_list = self.getAllPhotos(target['targetUserid'], 33, None, [])
            for i in photos_list:
                if hasattr(i, 'location'):
                    loc = {}
                    loc['plugin'] = "instagram"
                    loc['context'] = i.caption.text if i.caption else unicode('No Caption', 'utf-8')
                    loc['infowindow'] = self.constructContextInfoWindow(i)
                    loc['date'] = pytz.utc.localize(i.created_time)
                    loc['lat'] = i.location.point.latitude
                    loc['lon'] = i.location.point.longitude
                    loc['shortName'] = i.location.name
                    locations_list.append(loc)
            logger.debug(str(len(locations_list)) + " locations have been retrieved")
        except Exception, err:
            logger.error(err)
            logger.error("Error getting locations from instagram plugin")
        return locations_list, None

    def runConfigWizard(self):
        try:
            api = InstagramAPI(client_id=self.options_string['hidden_client_id'],
                               client_secret=self.options_string['hidden_client_secret'],
                               redirect_uri=self.options_string['redirect_uri'])
            url = api.get_authorize_login_url()
            self.wizard = QWizard()
            self.wizard.setWindowTitle("Instagram plugin configuration wizard")
            page1 = QWizardPage()
            layout1 = QVBoxLayout()
            txtArea = QLabel()
            txtArea.setText("Please copy the following link to your browser window. \n " +
                                  "Once you authenticate with Instagram you will be redirected to www.geocreepy.com and get your token. Copy the token to the input field below:")
            urlArea = QLineEdit()
            urlArea.setObjectName('urlArea')
            urlArea.setText(url)
            inputLink = QLineEdit()
            inputLink.setObjectName("inputLink")
            labelLink = QLabel("Your token value:")
            layout1.addWidget(txtArea)
            layout1.addWidget(urlArea)
            layout1.addWidget(labelLink)
            layout1.addWidget(inputLink)
            page1.setLayout(layout1)
            self.wizard.addPage(page1)
            self.wizard.resize(600, 400)
            if self.wizard.exec_():
                c = str(inputLink.text())
                if c:
                    try:
                        access_token = api.exchange_code_for_access_token(code=c)
                        self.options_string['hidden_access_token'] = access_token[0]
                        self.config.write()
                    except Exception, err:
                        self.showWarning("Error Getting Access Token",
                                         "Please verify that the link you pasted was correct. Try running the wizard again.")
                else:
                    self.showWarning("Error Getting Access Token",
                                     "Please verify that the link you pasted was correct. Try running the wizard again.")

        except Exception, err:
            logger.exception(err)

    def parseRedirectUrl(self, link):
        try:
            return parse_qs(urlparse(link).query)['code'][0]
        except Exception, err:
            logger.error(err)
            return None

    def showWarning(self, title, text):
        QMessageBox.warning(self.wizard, title, text)

    def constructContextInfoWindow(self, photo):
        html = unicode(self.options_string['infowindow_html'], 'utf-8')
        caption = photo.caption.text if photo.caption else unicode('No Caption', 'utf-8')
        return html.replace("@TEXT@", caption).replace("@DATE@", pytz.utc.localize(photo.created_time).strftime(
            "%Y-%m-%d %H:%M:%S %z")).replace("@PLUGIN@", u"instagram").replace("@LINK@", photo.link)


    def getLabelForKey(self, key):
        '''
        read the plugin_name.labels 
        file and try to get label text for the key that was asked
        '''
        if not self.labels:
            return key
        if key not in self.labels.keys():
            return key
        return self.labels[key]
