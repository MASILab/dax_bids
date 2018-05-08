""" Processor class define for Scan and Session."""

from builtins import object
from past.builtins import basestring

import logging
import re
import os
from uuid import uuid4

from . import XnatUtils, task
from . import processor_parser
from .errors import AutoProcessorError
from .dax_settings import DEFAULT_FS_DATATYPE, DEFAULT_DATATYPE


try:
    basestring
except NameError:
    basestring = str

__copyright__ = 'Copyright 2013 Vanderbilt University. All Rights Reserved'
__all__ = ['Processor', 'ScanProcessor', 'SessionProcessor', 'AutoProcessor']
# Logger for logs
LOGGER = logging.getLogger('dax')


class Processor(object):
    """ Base class for processor """
    def __init__(self, walltime_str, memreq_mb, spider_path,
                 version=None, ppn=1, env=None, suffix_proc='',
                 xsitype='proc:genProcData'):
        """
        Entry point of the Base class for processor.

        :param walltime_str: Amount of walltime to request for the process
        :param memreq_mb: Number of megabytes of memory to use
        :param spider_path: Fully qualified path to the spider to run
        :param version: Version of the spider
        :param ppn: Number of processors per job to use.
        :param env: Environment file to source.
        :param suffix_proc: Processor suffix (if desired)
        :param xsitype: the XNAT xsiType.
        :return: None

        """
        self.walltime_str = walltime_str  # 00:00:00 format
        self.memreq_mb = memreq_mb   # memory required in megabytes
        # default values:
        self.version = "1.0.0"
        # Suffix
        if suffix_proc and suffix_proc[0] != '_':
            self.suffix_proc = '_%s' % suffix_proc
        else:
            self.suffix_proc = suffix_proc
        self.suffix_proc = re.sub('[^a-zA-Z0-9]', '_', self.suffix_proc)
        self.name = None
        self.spider_path = spider_path
        self.ppn = ppn
        if env:
            self.env = env
        else:
            self.env = os.path.join(os.environ['HOME'], '.bashrc')
        self.xsitype = xsitype
        # getting name and version from spider_path
        self.set_spider_settings(spider_path, version)
        # if suffix_proc is empty, set it to "" for the spider call:
        if not suffix_proc:
            self.suffix_proc = ''

    # get the spider_path right with the version:
    def set_spider_settings(self, spider_path, version):
        """
        Method to set the spider version, path, and name from filepath

        :param spider_path: Fully qualified path and file of the spider
        :param version: version of the spider
        :return: None

        """
        if version:
            # get the proc_name
            proc_name = os.path.basename(spider_path)[7:-3]
            # remove any version if there is one
            proc_name = re.split("/*_v[0-9]/*", proc_name)[0]
            # setting the version and name of the spider
            self.version = version
            nformat = '''{procname}_v{version}{suffix}'''
            self.name = nformat.format(procname=proc_name,
                                       version=self.version.split('.')[0],
                                       suffix=self.suffix_proc)
            sformat = '''Spider_{procname}_v{version}.py'''
            spider_name = sformat.format(procname=proc_name,
                                         version=version.replace('.', '_'))
            self.spider_path = os.path.join(os.path.dirname(spider_path),
                                            spider_name)
        else:
            self.default_settings_spider(spider_path)

    def default_settings_spider(self, spider_path):
        """
        Get the default spider version and name

        :param spider_path: Fully qualified path and file of the spider
        :return: None

        """
        # set spider path
        self.spider_path = spider_path
        # set the name and the version of the spider
        if len(re.split("/*_v[0-9]/*", spider_path)) > 1:
            basename = os.path.basename(spider_path)
            self.version = basename[7:-3].split('_v')[-1].replace('_', '.')
            spidername = basename[7:-3]
            self.name = '''{procname}_v{version}{suffix}'''.format(
                procname=re.split("/*_v[0-9]/*", spidername)[0],
                version=self.version.split('.')[0], suffix=self.suffix_proc)
        else:
            self.name = os.path.basename(spider_path)[7:-3] + self.suffix_proc

    # has_inputs - does this object have the required inputs?
    # e.g. NIFTI format of the required scan type and quality
    #      and are there no conflicting inputs.
    # i.e. only 1 required by 2 found?
    # other arguments here, could be Proj/Subj/Sess/Scan/Assessor depending
    # on processor type?
    def has_inputs(self):
        """
        Check to see if the spider has all the inputs necessary to run.

        :raises: NotImplementedError if user does not override
        :return: None

        """
        raise NotImplementedError()

    # should_run - is the object of the proper object type?
    # e.g. is it a scan? and is it the required scan type?
    # e.g. is it a T1?
    # other arguments here, could be Proj/Subj/Sess/Scan/Assessor depending
    # on processor type?
    def should_run(self):
        """
        Responsible for determining if the assessor should shouw up in session.

        :raises: NotImplementedError if not overridden.
        :return: None

        """
        raise NotImplementedError()

    def build_cmds(self, cobj, dir):

        """
        Build the commands that will go in the PBS/SLURM script
        :raises: NotImplementedError if not overridden from base class.
        :return: None
        """
        raise NotImplementedError()


class ScanProcessor(Processor):
    """ Scan Processor class for processor on a scan on XNAT """
    def __init__(self, scan_types, walltime_str, memreq_mb, spider_path,
                 version=None, ppn=1, env=None, suffix_proc='',
                 full_regex=False):
        """
        Entry point of the ScanProcessor Class.

        :param scan_types: Types of scans that the spider should run on
        :param walltime_str: Amount of walltime to request for the process
        :param memreq_mb: Amount of memory in MB to request for the process
        :param spider_path: Absolute path to the spider
        :param version: Version of the spider (taken from the file name)
        :param ppn: Number of processors per node to request
        :param env: Environment file to source
        :param suffix_proc: Processor suffix
        :param full_regex: use full regex
        :return: None

        """
        super(ScanProcessor, self).__init__(walltime_str, memreq_mb,
                                            spider_path, version, ppn,
                                            env, suffix_proc)
        self.full_regex = full_regex
        if isinstance(scan_types, list):
            self.scan_types = scan_types
        elif isinstance(scan_types, basestring):
            if scan_types == 'all':
                self.scan_types = 'all'
            else:
                self.scan_types = scan_types.split(',')
        else:
            self.scan_types = []

    def has_inputs(self):
        """
        Method to check and see that the process has all of the inputs
         that it needs to run.

        :raises: NotImplementedError if not overridden.
        :return: None

        """
        raise NotImplementedError()

    def get_assessor_name(self, cscan):
        """
        Returns the label of the assessor

        :param cscan: CachedImageScan object from XnatUtils
        :return: String of the assessor label

        """
        scan_dict = cscan.info()
        subj_label = scan_dict['subject_label']
        sess_label = scan_dict['session_label']
        proj_label = scan_dict['project_label']
        scan_label = scan_dict['scan_label']
        assr_name = '-x-'.join([proj_label, subj_label, sess_label, scan_label,
                                self.name])

        # Check if shared project:
        csess = cscan.parent()
        proj_shared = csess.has_shared_project()
        assr_name_shared = None
        if proj_shared is not None:
            assr_name_shared = '-x-'.join([proj_shared, subj_label, sess_label,
                                           scan_label, self.name])

        # Look for existing assessor
        assr_label = assr_name
        for assr in csess.assessors():
            if assr_name_shared is not None and \
               assr.info()['label'] == assr_name_shared:
                assr_label = assr_name_shared
                break
            if assr.info()['label'] == assr_name:
                break

        return assr_label

    def get_assessor(self, cscan):
        """
        Returns the assessor object depending on cscan and the assessor label.

        :param cscan: CachedImageScan object from XnatUtils
        :return: String of the assessor label

        """
        assessor_name = self.get_assessor_name(cscan)

        # Look for existing assessor
        csess = cscan.parent()
        p_assr = None
        for assr in csess.assessors():
            if assr.info()['label'] == assessor_name:
                p_assr = assr
                break

        return p_assr, assessor_name

    def get_task(self, cscan, upload_dir):
        """
        Get the Task object

        :param intf: XNAT interface (pyxnat.Interface class)
        :param cscan: CachedImageScan object from XnatUtils
        :param upload_dir: the directory to put the processed data when the
         process is done
        :return: Task object

        """
        assessor_name = self.get_assessor_name(cscan)
        scan = cscan.full_object()
        assessor = scan.parent().assessor(assessor_name)
        return task.Task(self, assessor, upload_dir)

    def should_run(self, scan_dict):
        """
        Method to see if the assessor should appear in the session.

        :param scan_dict: Dictionary of information about the scan
        :return: True if it should run, false if it shouldn't

        """
        if self.scan_types == 'all':
            return True
        else:
            for expression in self.scan_types:
                regex = XnatUtils.extract_exp(expression, self.full_regex)
                if regex.match(scan_dict['scan_type']):
                    return True
            return False


class SessionProcessor(Processor):
    """ Session Processor class for processor on a session on XNAT """
    def __init__(self, walltime_str, memreq_mb, spider_path, version=None,
                 ppn=1, env=None, suffix_proc=''):
        """
        Entry point for the session processor

        :param walltime_str: Amount of walltime to request for the process
        :param memreq_mb: Amount of memory in MB to request for the process
        :param spider_path: Absolute path to the spider
        :param version: Version of the spider (taken from the file name)
        :param ppn: Number of processors per node to request
        :param env: Environment file to source
        :param suffix_proc: Processor suffix
        :return: None

        """
        super(SessionProcessor, self).__init__(walltime_str, memreq_mb,
                                               spider_path, version, ppn,
                                               env, suffix_proc)

    def has_inputs(self):
        """
        Check to see that the session has the required inputs to run.

        :raises: NotImplementedError if not overriden from base class.
        :return: None
        """
        raise NotImplementedError()

    def should_run(self, session_dict):
        """
        By definition, this should always run, so it just returns true
         with no checks

        :param session_dict: Dictionary of session information for
         XnatUtils.list_experiments()
        :return: True

        """
        return True

    def get_assessor_name(self, csess):
        """
        Returns the label of the assessor

        :param csess: CachedImageSession object from XnatUtils
        :return: String of the assessor label

        """
        session_dict = csess.info()
        proj_label = session_dict['project_id']
        subj_label = session_dict['subject_label']
        sess_label = session_dict['label']
        assr_name = '-x-'.join([proj_label, subj_label, sess_label, self.name])

        # Check if shared project:
        proj_shared = csess.has_shared_project()
        assr_name_shared = None
        if proj_shared is not None:
            assr_name_shared = '-x-'.join([proj_shared, subj_label, sess_label,
                                           self.name])

        # Look for existing assessor
        assr_label = assr_name
        for assr in csess.assessors():
            if assr_name_shared is not None and \
               assr.info()['label'] == assr_name_shared:
                assr_label = assr_name_shared
                break
            if assr.info()['label'] == assr_name:
                break

        return assr_label

    def get_assessor(self, csess):
        """
        Returns the assessor object depending on csess and the assessor label.

        :param csess: CachedImageSession object from XnatUtils
        :return: String of the assessor label

        """
        # TODO: BenM/id_refactor/currently returns null if the assessor doesn't
        # exist; this adds unnecessary complexity downstream - consider adding
        # a method that returns assessors that need construction and one for
        # assessors that exist
        assessor_name = self.get_assessor_name(csess)

        # Look for existing assessor
        p_assr = None
        for assr in csess.assessors():
            if assr.info()['label'] == assessor_name:
                p_assr = assr
                break

        return p_assr, assessor_name

    def get_task(self, csess, upload_dir):
        """
        Return the Task object

        :param csess: CachedImageSession from XnatUtils
        :param upload_dir: directory to put the data after run on the node
        :return: Task object of the assessor

        """
        assessor_name = self.get_assessor_name(csess)
        session = csess.full_object()
        assessor = session.assessor(assessor_name)
        return task.Task(self, assessor, upload_dir)


class AutoProcessor(Processor):
    """ Auto Processor class for AutoSpider using YAML files"""
    def __init__(self, xnat, yaml_source, user_inputs=None):
        """
        Entry point for the auto processor
        :param xnat: xnat context object (XnatUtils in production contexts)
        :param yaml_source: dictionary containing source_type -> string,\
                            source_id -> string, document -> yaml document
        :param user_inputs: a dictionary of user overrides to the yaml\
                            source document
        :return: None

        """
        if not xnat:
            raise AutoProcessorError("Parameter 'xnat' must be provided")
        if not yaml_source:
            raise AutoProcessorError("Parameter 'yaml_source' must be provided")

        self.xnat = xnat
        self.user_overrides = dict()
        self.extra_user_overrides = dict()

        self._read_yaml(yaml_source)

        # Edit the values from user inputs:
        if user_inputs is not None:
            self._edit_inputs(user_inputs, yaml_source)

        self.parser = processor_parser.ProcessorParser(yaml_source.contents)

        # Set up attrs:
        self.walltime_str = self.attrs.get('walltime')
        self.memreq_mb = self.attrs.get('memory')
        self.ppn = self.attrs.get('ppn', 1)
        self.env = self.attrs.get('env', None)
        self.xsitype = self.attrs.get('xsitype', 'proc:genProcData')
        self.full_regex = self.attrs.get('fullregex', False)
        self.suffix = self.attrs.get('suffix', None)

        # Set scan info if scan auto processor
        if self.type == 'scan':
            if self.scan_nb is None:
                err = 'YAML document {} does not have a scan_nb defined.'
                raise AutoProcessorError(err.format(yaml_source['source_id']))

            _docs = [_doc for _doc in self.xnat_inputs.get('scans')
                     if self.scan_nb in list(_doc.keys())]
            if len(_docs) == 1:
                self.scaninfo = _docs[0]
            else:
                err = 'YAML document {} does not have a valid scan_nb defined.\
No xnat.scans.{} in inputs found.'
                raise AutoProcessorError(err.format(yaml_source['source_id'],
                                                    self.scan_nb))


    def _edit_inputs(self, user_inputs, yaml_source):
        """
        Method to edit the inputs from the YAML file by the user inputs.

        :param user_inputs: dictionary of tag, value. E.G:
            user_inputs = {'default.spider_path': /.../Spider....py'}
        """
        for key, val in list(user_inputs.items()):
            tags = key.split('.')
            if key.startswith('inputs.default'):
                # change value in inputs
                if tags[-1] in list(self.user_overrides.keys()):
                    self.user_overrides[tags[-1]] = val
                elif tags[-1] in list(self.extra_user_overrides.keys()):
                    self.extra_user_overrides[tags[-1]] = val
                else:
                    msg = 'key {} not found in the default inputs for \
auto processor defined by yaml file {}'
                    LOGGER.warn(msg.format(tags[-1], yaml_source.source_id))
            elif key.startswith('inputs.xnat'):
                # change value in self.xnat_inputs
                if tags[2] in list(self.xnat_inputs.keys()):
                    # scan number or assessor number (e.g: scan1)
                    for obj in self.xnat_inputs[tags[2]]:
                        if tags[3] in list(obj.keys()) and \
                           tags[4] in list(obj.keys()):
                            if tags[4] == 'resources':
                                msg = 'You can not change the resources \
tag from the processor yaml file {}. Unauthorised operation.'
                                LOGGER.warn(msg.format(yaml_source.source_id))
                            else:
                                obj[tags[4]] = val
                else:
                    msg = 'key {} not found in the xnat inputs for auto \
processor defined by yaml file {}'
                    LOGGER.warn(msg.format(tags[3], yaml_source.source_id))
            elif key.startswith('attrs'):
                # change value in self.attrs
                if tags[-1] in list(self.attrs.keys()):
                    self.attrs[tags[-1]] = val
                else:
                    msg = 'key {} not found in the attrs for auto processor \
defined by yaml file {}'
                    LOGGER.warn(msg.format(tags[-1], yaml_source.source_id))


    def _read_yaml(self, yaml_source):
        """
        Method to parse the processor arguments and their default values.

        :param yaml_source: YamlDoc object containing the yaml file contents
        """
        if yaml_source.source_type is None:
            raise AutoProcessorError('Empty yaml source provided')

        doc = yaml_source.contents

        # Set Inputs from Yaml
        self._check_default_keys(yaml_source.source_id, doc)
        self.attrs = doc.get('attrs')
        self.command = doc.get('command')
        inputs = doc.get('inputs')
        self.xnat_inputs = inputs.get('xnat')
        for key, value in list(inputs.get('default').items()):
            # If value is a key in command
            k_str = '{{{}}}'.format(key)
            if k_str in self.command:
                self.user_overrides[key] = value
            else:
                if isinstance(value, bool) and value is True:
                    self.extra_user_overrides[key] = ''
                elif value and value != 'None':
                    self.extra_user_overrides[key] = value

        # Getting proctype from Yaml
        self.proctype, self.version = self.xnat.get_proctype(
            self.user_overrides.get('spider_path'),
            self.attrs.get('suffix', None))

        # Set attributs:
        self.spider_path = self.user_overrides.get('spider_path')
        self.name = self.proctype
        self.type = self.attrs.get('type')
        self.scan_nb = self.attrs.get('scan_nb', None)


    def _check_default_keys(self, source_id, doc):
        """ Static method to raise error if key not found in dictionary from
        yaml file.

        :param source_id: dictionary containing source_type -> string,\
                            source_id -> string, document -> yaml document
        :param key: key to check in the doc
        """
        # first level
        for key in ['inputs', 'command', 'attrs']:
            self._raise_yaml_error_if_no_key(doc, source_id, key)
        # Second level in inputs and attrs:
        inputs = doc.get('inputs')
        attrs = doc.get('attrs')
        for _doc, key in [(inputs, 'default'), (inputs, 'xnat'),
                          (attrs, 'type'), (attrs, 'memory'),
                          (attrs, 'walltime')]:
            self._raise_yaml_error_if_no_key(_doc, source_id, key)
        if attrs['type'] == 'scan':
            self._raise_yaml_error_if_no_key(attrs, source_id, 'scan_nb')
        # third level for default:
        default = doc.get('inputs').get('default')
        for key in ['spider_path']:
            self._raise_yaml_error_if_no_key(default, source_id, key)


    @ staticmethod
    def _raise_yaml_error_if_no_key(doc, source_id, key):
        """Method to raise an execption if the key is not in the dict

        :param doc: dict to check
        :param source_id: YAML source identifier string for logging
        :param key: key to search
        """
        if key not in list(doc.keys()):
            err = 'YAML source {} does not have {} defined. See example.'
            raise AutoProcessorError(err.format(source_id, key))


    # TODO:BenM/assessor_of_assessor/deprecated/keep this method around until we
    # have removed/refactored any backwards-compatibility code for the old
    # naming mechanism
    def get_assessor_name(self, cobj):
        """
        Returns the label of the assessor

        :param csobj: CachedImageSession or CachedImageScan object depending
                      on the level
        :return: String of the assessor label

        """
        csess = cobj.session()

        obj_info = cobj.info()
        labels = [obj_info['project_id'], obj_info['subject_label'],
                  obj_info['session_label']]
        if self.type == 'scan':
            labels.append(obj_info['scan_label'])
        labels.append(self.proctype)
        assr_name = '-x-'.join(labels)

        # Check if shared project:
        proj_shared = csess.has_shared_project()
        assr_name_shared = None
        if proj_shared is not None:
            labels[0] = proj_shared
            assr_name_shared = '-x-'.join(labels)

        # Look for existing assessor
        assr_label = assr_name
        for assr in csess.assessors():
            if assr_name_shared is not None and \
               assr.info()['label'] == assr_name_shared:
                assr_label = assr_name_shared
                break
            if assr.info()['label'] == assr_name:
                break

        return assr_label

    # TODO: BenM/assessor_of_assessor/assessors are described by a type/inputs
    # tuple now, so we need to check the inputs of each assessor of the
    # appropriate type
    def get_assessor_mapping(self, csess):
        # parse the contents of the session and determine what assessors need to
        # be constructed
        self.parser.parse_session(csess)
        return self.parser.assessor_parameter_map

    # TODO: BenM/assessor_of_assessor/remove once upgrade strategy (if any) has
    # been determined and this code is no longer needed
    def get_assessor(self, cobj):
        """
        Returns the assessor object depending on cobj and the assessor label.

        :param cscan: CachedImageScan object from XnatUtils
        :return: String of the assessor label

        """
        assessor_name = self.get_assessor_name(cobj)

        # Look for existing assessor
        csess = cobj.session()
        p_assr = None
        for assr in csess.assessors():
            if assr.info()['label'] == assessor_name:
                p_assr = assr
                break

        return p_assr, assessor_name

    # def get_task(self, cobj, upload_dir):
    #     """
    #     Return the Task object
    #
    #     :param intf: XNAT interface see pyxnat.Interface
    #     :param cobj: CachedImageSession or Scan from XnatUtils
    #     :param upload_dir: directory to put the data after run on the node
    #     :return: Task object of the assessor
    #
    #     """
    #     assessor_name = self.get_assessor_name(cobj)
    #     obj = cobj.full_object()
    #     if cobj.entity_type() == 'session':
    #         assessor = obj.assessor(assessor_name)
    #     elif cobj.entity_type() == 'scan':
    #         assessor = obj.parent().assessor(assessor_name)
    #     return task.Task(self, assessor, upload_dir)

    def should_run(self, obj_dict):
        """
        Method to see if the assessor should appear in the session.

        :param obj_dict: Dictionary of information about the scan or sesion
        :return: True if it should run, false if it shouldn't

        """
        # TODO: BenM/assessor_of_assessor/
        # this method checks
        if 'scan_type' in obj_dict:
            scantypes = self.scaninfo.get('types', '').split(',')
            if scantypes == 'all':
                return True
            else:
                for expression in scantypes:
                    regex = self.xnat.extract_exp(expression, self.full_regex)
                    if regex.match(obj_dict['scan_type']):
                        return True
                return False
        else:
            # By definition, this should always run, so it just returns true
            # with no checks for session
            return True

    def has_inputs(self, cobj):
        """Method to check the inputs.

        By definition:
            status = 0  -> NEED_INPUTS,
            status = 1  -> NEED_TO_RUN
            status = -1 -> NO_DATA
            qcstatus needs a value only when -1 or 0.
        You need to set qcstatus to a short string that explain
        why it's no ready to run. e.g: No NIFTI

        :param cobj: cached object define in dax.XnatUtils (Session or Scan)
                     (see XnatUtils in dax for information)
        :return: status, qcstatus
        """
        # TODO: BenM/assessor_of_assessor/replace with processor_parser
        # functionality
        # If Scan assessor, check that the scan has inputs
        csess = cobj.session()
        if cobj.entity_type() == 'scan':
            if self.xnat.is_cscan_unusable(cobj):
                    return -1, 'Scan unusable'

            for res_dict in self.scaninfo.get('resources', list()):
                resource = res_dict.get('resource')
                if not self.xnat.has_resource(cobj, resource):
                    msg = '{}: {} not found.'
                    LOGGER.debug(msg.format(self.proctype, resource))
                    return 0, 'No {}'.format(resource)

        # Check xnat inputs set in YAML file:
        # Scans:
        for scan_in in self.xnat_inputs.get('scans', list()):
            if self.scan_nb not in list(scan_in.keys()):
                scantypes = scan_in.get('types').split(',')
                nargs = scan_in.get('nargs', False)
                needs_qc = scan_in.get('needs_qc', True)
                doc_res = scan_in.get('resources', list())
                resources = [_doc.get('resource') for _doc in doc_res
                             if _doc.get('required', True)]
                status, qcstatus = self._check_xnat_cobj(
                    csess, scantypes, 'scan', nargs, resources, needs_qc)
                if status == 0 or status == -1:
                    return status, qcstatus
        # Assessors:
        for assr_in in self.xnat_inputs.get('assessors', list()):
            proctypes = assr_in.get('proctypes').split(',')
            nargs = assr_in.get('nargs', False)
            needs_qc = assr_in.get('needs_qc', True)
            doc_res = assr_in.get('resources', list())
            resources = [_doc.get('resource') for _doc in doc_res
                         if _doc.get('required', True)]
            status, qcstatus = self._check_xnat_cobj(
                csess, proctypes, 'assessor', nargs, resources, needs_qc)
            if status == 0 or status == -1:
                return status, qcstatus

        return 1, None

    def _check_xnat_cobj(self, csess, sp_types, otype='scan', nargs=False,
                         resources=list(), needs_qc=True):
        """Method to check if in a csess you have the right inputs (scans)

        :param csess: CachedImageSession to check
        :param sp_types: list of scan types or proctypes to look for
        :param nargs: allow more than one scans of this type
        :param resources: resources to check on XNAT
        :param needs_qc: if we are looking for object with qc that passed
        :return: status, qcstatus
        """
        good_cobjs = list()
        if otype == 'scan':
            good_cobjs = self.xnat.get_good_cscans(csess, sp_types, needs_qc)
        else:
            good_cobjs = self.xnat.get_good_cassr(csess, sp_types, needs_qc)

        if not good_cobjs:
            msg = '{}: No {} {} found.'
            LOGGER.debug(msg.format(self.name, ','.join(sp_types), otype))
            # Return NO DATA if scan and 0 if assessor
            if otype == 'scan':
                return -1, 'No {} found'.format(','.join(sp_types))
            else:
                return 0, 'No {} found'.format(','.join(sp_types))
        elif nargs is False and len(good_cobjs) > 1:
            msg = '{}: Too many {} {} found.'
            LOGGER.debug(msg.format(self.name, ','.join(sp_types),
                                    '{}s'.format(otype)))
            return 0, 'Too many {} found'.format(','.join(sp_types))

        # Check resources if set:
        if resources is not None and len(resources) > 0:
            for cobj in good_cobjs:
                for res in resources:
                    if otype == 'scan':
                        label = cobj.info()['ID']
                        _type = cobj.info()['type']
                    else:
                        label = cobj.info()['label']
                        _type = cobj.info()['proctype']
                    if not self.xnat.has_resource(cobj, res):
                        msg = '{}: missing resource {} for {}.'
                        LOGGER.debug(msg.format(self.proctype, res, label))
                        return 0, 'Missing {} on {}'.format(res, _type)
        return 1, None

#     def get_xnat_path(self, cobjs, resource, required=True, fpath=None):
#         """Method to get the file path on XNAT for the scans
#
#         :param cobjs: list of cobjs (assessor or scan) in dax.XnatUtils
#                       (see XnatUtils in dax for information)
#         :param resource: name of the resource
#         :param fpath: filepath to get
#         :return: list of paths
#         """
#         filepaths = list()
#         assr_tmp = 'xnat:/project/{0}/subject/{1}/experiment/{2}/assessor/{3}/\
# resource/{4}'
#         scan_tmp = 'xnat:/project/{0}/subject/{1}/experiment/{2}/scan/{3}/\
# resource/{4}'
#
#         for cobj in cobjs:
#             obj_info = cobj.info()
#             if cobj.entity_type() == 'assessor':
#                 label = obj_info['label']
#                 path_tmp = assr_tmp
#             elif cobj.entity_type() == 'scan':
#                 label = obj_info['ID']
#                 path_tmp = scan_tmp
#             if resource in [res['label'] for res in cobj.get_resources()]:
#                 x_path = path_tmp.format(obj_info['project_id'],
#                                          obj_info['subject_label'],
#                                          obj_info['session_label'],
#                                          label, resource)
#                 if fpath:
#                     x_path = '{}/files/{}'.format(x_path, fpath)
#                 filepaths.append(x_path)
#             elif required:
#                 msg = 'No resource {} found for {} in session {}.'
#                 LOGGER.debug(msg.format(resource, label,
#                                         obj_info['session_label']))
#         return filepaths

    # TODO: BenM/assessor_of_assessor/this method is no longer suitable for
    # execution on a single assessor, as it generates commands for the whole
    # session. In any case, the command should be written out to the xnat
    # assessor schema so that it can simply be launched, rather than performing
    # this reconstruction each time the dax launch command is called
    def get_cmds(self, cassr, jobdir):
        """Method to generate the spider command for cluster job.

        :param assessor: pyxnat assessor object
        :param jobdir: jobdir where the job's output will be generated
        :return: command to execute the spider in the job script
        """
        # Add the jobidr and the assessor label:
        assr_label = cassr.label()

        # Get the csess:
        csess = cassr.session()

        # TODO: BenM/assessor_of_assessors/parse each scan / assessor and
        # any select statements and generate one or more corresponding commands

        self.parser.parse_session(csess)
        self.parser.command_params

        # combine the user overrides with the input parameters for each
        # distinct command
        commands = []
        for variable_set in self.parser.command_params:
            combined_params = {}
            for k, v in variable_set.iteritems():
                combined_params[k] = v
            for k, v in self.user_overrides.iteritems():
                combined_params[k] = v

            cmd = self.command.format(combined_params)

            for key, value in list(self.extra_user_overrides.items()):
                cmd = '{} --{} {}'.format(cmd, key, value)

            # TODO: BenM/assessor_of_assessor/each assessor is separate and
            # has a different label; change the code to fetch the label from
            # the assessor
            # Add assr and jobidr:
            if ' -a ' not in cmd and ' --assessor ' not in cmd:
                cmd = '{} -a {}'.format(cmd, assr_label)
            if ' -d ' not in cmd:
                cmd = '{} -d {}'.format(cmd, jobdir)

            commands.append(cmd)

        return commands

    def create_assessor(self, xnatsession, inputs):
        while True:
            guid = str(uuid4())
            assessor = xnatsession.assessor(guid)
            if not assessor.exists():
                kwargs = {}
                if self.xsitype.lower() == DEFAULT_FS_DATATYPE.lower():
                    fsversion = '{}/fsversion'.format(self.xsitype.lower())
                    kwargs[fsversion] = 0
                elif self.xsitype.lower() == DEFAULT_DATATYPE.lower():
                    proctype = '{}/proctype'.format(self.xsitype.lower())
                    kwargs[proctype] = self.name
                    procversion = '{}/procversion'.format(self.xsitype.lower())
                    kwargs[procversion] = self.version
                assessor.create(assessors=self.xsitype.lower(),
                                ID=guid,
                                **kwargs)
                break

    def _inputs_to_document(self, inputs):
        



        # TODO: BenM/assessor_of_assessor / replace with processor_parser
        # functionality - one per row in the parameter matrix
        # Get the data from xnat for the xnat_inputs:
        # Scans:
        # for scan_in in self.xnat_inputs.get('scans', list()):
        #     scantypes = scan_in.get('types').split(',')
        #     needs_qc = scan_in.get('needs_qc', True)
        #     resources = scan_in.get('resources', list())
        #     if self.scan_nb not in list(scan_in.keys()):
        #         self._append_xnat_cobj(csess, scantypes, resources, needs_qc,
        #                                'scan')
        #     else:
        #         cprocscan = [cscan for cscan in csess.scans()
        #                      if cscan.info()['ID'] == scan_label]
        #         self._get_xnat_procscan(cprocscan, resources)
        #
        # # Assessors:
        # for assr_in in self.xnat_inputs.get('assessors', list()):
        #     proctypes = assr_in.get('proctypes').split(',')
        #     needs_qc = assr_in.get('needs_qc', True)
        #     resources = assr_in.get('resources', list())
        #     self._append_xnat_cobj(csess, proctypes, resources, needs_qc,
        #                            'assessor')
        #
        # cmd = self.command.format(**self.user_overrides)
        #
        # for key, value in list(self.extra_user_overrides.items()):
        #     cmd = '{} --{} {}'.format(cmd, key, value)
        #
        # # Add assr and jobidr:
        # if ' -a ' not in cmd and ' --assessor ' not in cmd:
        #     cmd = '{} -a {}'.format(cmd, assr_label)
        # if ' -d ' not in cmd:
        #     cmd = '{} -d {}'.format(cmd, jobdir)
        #
        # return [cmd]

    # TODO: BenM/assessor_of_assessor/replace with processor_parser
    # functionality; one call per variable per row of parameter matrix
    # def _append_xnat_cobj(self, csess, sp_types, resources, needs_qc=True,
    #                       otype='scan'):
    #     """Method to append XNAT cobj info to inputs for command.
    #
    #     :param csess: CachedImageSession from XnatUtils
    #     :param sp_types: types of scan or assessor to look for
    #     :param resources: list of resources from YAML file with var
    #     :param needs_qc: if we are looking for object with qc that passed
    #     """
    #     good_cobjs = list()
    #     if otype == 'scan':
    #         good_cobjs = self.xnat.get_good_cscans(csess, sp_types, needs_qc)
    #     else:
    #         good_cobjs = self.xnat.get_good_cassr(csess, sp_types, needs_qc)
    #
    #     for res_l in resources:
    #         if 'varname' not in list(res_l.keys()):
    #             LOGGER.warn("No Key 'varname' found for resource in YAML.")
    #         else:
    #             _in = self.get_xnat_path(good_cobjs, res_l.get('resource'),
    #                                      required=res_l.get('required', True),
    #                                      fpath=res_l.get('filepath', None))
    #             self.user_overrides[res_l.get('varname')] = ','.join(_in)

    # def _get_xnat_procscan(self, cprocscan, resources):
    #     """Method to append XNAT cobj info to inputs for command.
    #
    #     :param cscan: CachedImageScan related to the assessor
    #     :param resources: list of resources from YAML file with var
    #     """
    #     for res_info in resources:
    #         if 'varname' not in list(res_info.keys()):
    #             LOGGER.warn("No Key 'varname' found for resource in YAML.")
    #         else:
    #             _in = self.get_xnat_path(cprocscan, res_info.get('resource'),
    #                                      fpath=res_info.get('filepath', None))
    #             self.user_overrides[res_info.get('varname')] = ','.join(_in)


def processors_by_type(proc_list):
    """
    Organize the processor types and return a list of session processors
     first, then scan

    :param proc_list: List of Processor classes from the DAX settings file
    :return: List of SessionProcessors, and list of ScanProcessors

    """
    sess_proc_list = list()
    scan_proc_list = list()

    # Build list of processors by type
    if proc_list is not None:
        for proc in proc_list:
            if issubclass(proc.__class__, ScanProcessor):
                scan_proc_list.append(proc)
            elif issubclass(proc.__class__, SessionProcessor):
                sess_proc_list.append(proc)
            elif issubclass(proc.__class__, AutoProcessor):
                if proc.type == 'scan':
                    scan_proc_list.append(proc)
                else:
                    sess_proc_list.append(proc)
            else:
                LOGGER.warn('unknown processor type: %s' % proc)

    return sess_proc_list, scan_proc_list
