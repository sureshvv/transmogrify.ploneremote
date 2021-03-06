import urllib
import logging

from zope.interface import classProvides, implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import defaultMatcher
from collective.transmogrifier.utils import Condition, Expression

from Products.CMFCore.utils import getToolByName
from Products.CMFCore.WorkflowCore import WorkflowException
import xmlrpclib

from base import AbstractRemoteCommand,PathBasedAbstractRemoteCommand


class RemoteWorkflowUpdaterSection(PathBasedAbstractRemoteCommand):
    """
    Do remote workflow state transition using Plone HTTP API.
    Trigger the same HTTP GET query as Workflow menu does in the user
    interface.
    """
    classProvides(ISectionBlueprint)
    implements(ISection)

    def readOptions(self, options):
        """ Read options give in pipeline.cfg
        """

        # Call parent 
        PathBasedAbstractRemoteCommand.readOptions(self, options)
        
        # Remote site / object URL containing HTTP Basic Auth username and password 
        self.pathkey = defaultMatcher(options, 'path-key', self.name, 'path')
        self.transitionskey = defaultMatcher(options, 'transitions-key', self.name,
                                             'transitions')


    def __iter__(self):
        self.checkOptions()
        for item in self.previous:
            if not self.target:
                yield item
                continue
            keys = item.keys()
            # Apply defaultMatcher() function to extract necessary data
            # 1) which item will be transitioned
            # 2) with which transition
            pathkey = self.pathkey(*keys)[0]
            transitionskey = self.transitionskey(*keys)[0]
            if not (pathkey and transitionskey):  # not enough info
                yield item
                continue

            path, transitions = item[pathkey], item[transitionskey]
            proxy = xmlrpclib.ServerProxy(self.constructRemoteURL(item))
            if not self.condition(item, proxy=proxy):
                self.logger.debug('%s skipping (condition)'%(path))
                yield item; continue

            if isinstance(transitions, basestring):
                transitions = (transitions,)


            remote_url = urllib.basejoin(self.target, path)
            if not remote_url.endswith("/"):
                remote_url += "/"

            # hacky way to get available transitions so we can avoid updating content
            f = urllib.urlopen(urllib.basejoin(remote_url,'view'))
            html = f.read()

            for transition in transitions:
                action = "content_status_modify?workflow_action=" + transition
                transition_trigger_url = urllib.basejoin(remote_url, action)
                if action not in html:
                    self.logger.debug('%s skipping (no action)'%(path))
                    continue

                self.logger.debug("%s performing transition '%s'" % (path,
                    transition))
                from httplib import HTTPException
                try:
                    urllib.urlopen(transition_trigger_url)
                    # f = urllib.urlopen(transition_trigger_url)
                    # data = f.read()
                    # XXX Keep going!
                    ## Use Plone not found page signature to detect bad URLs
                    #if "Please double check the web address" in data:
                    #    import pdb ; pdb.set_trace()
                    #    raise RuntimeError("Bad remote URL:" +
                    #transition_trigger_url)

                except HTTPException:
                    # Other than HTTP 200 OK should end up here,
                    # unless URL is broken in which case Plone shows
                    # "Your content was not found page"
                    self.logger.error("fail")
                    msg = "Remote workflow transition failed %s->%s" % (path,
                        transition)
                    self.logger.log(logging.ERROR, msg, exc_info=True)
            yield item
