import os
import sys
import copy
import logging
import warnings
import subprocess
import shutil
from pprint import pformat
from yggdrasil import platform, tools, backwards
from yggdrasil.config import ygg_cfg, locate_file, update_language_config
from yggdrasil.components import import_component
from yggdrasil.drivers.Driver import Driver
from threading import Event
try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x


class ModelDriver(Driver):
    r"""Base class for Model drivers and for running executable based models.

    Args:
        name (str): Driver name.
        args (str or list): Argument(s) for running the model on the command
            line. This should be a complete command including the necessary
            executable and command line arguments to that executable.
        products (list, optional): Paths to files created by the model that
            should be cleaned up when the model exits. Entries can be absolute
            paths or paths relative to the working directory. Defaults to [].
        is_server (bool, optional): If True, the model is assumed to be a server
            and an instance of :class:`yggdrasil.drivers.ServerDriver`
            is started. Defaults to False.
        client_of (str, list, optional): The names of ne or more servers that
            this model is a client of. Defaults to empty list.
        overwrite (bool, optional): If True, any existing model products
            (compilation products, wrapper scripts, etc.) are removed prior to
            the run. If False, the products are not removed. Defaults to True.
            Setting this to False can improve the performance, particularly for
            models that take a long time to compile, but this should only be
            done once the model has been fully debugged to ensure that each run
            is tested on a clean copy of the model. The value of this keyword
            also determines whether or not products are removed after a run.
        preserve_cache (bool, optional): If True model products will be kept
            following the run, otherwise all products will be cleaned up.
            Defaults to False. This keyword is superceeded by overwrite.
        with_strace (bool, optional): If True, the command is run with strace (on
            Linux) or dtrace (on MacOS). Defaults to False.
        strace_flags (list, optional): Flags to pass to strace (or dtrace).
            Defaults to [].
        with_valgrind (bool, optional): If True, the command is run with valgrind.
            Defaults to False.
        valgrind_flags (list, optional): Flags to pass to valgrind. Defaults to [].
        model_index (int, optional): Index of model in list of models being run.
            Defaults to 0.
        **kwargs: Additional keyword arguments are passed to parent class.

    Class Attributes:
        language (str): Primary name for the programming language that this
            compiler should be used for.
        language_aliases (list): Additional/alternative names that the language
            may be known by.
        language_ext (list): Extensions for programs written in the target
            language.
        base_languages (list): Other programming languages that this driver
            and the interpreter for the target language are dependent on (e.g.
            Matlab models require Python).
        executable_type (str): 'compiler' or 'interpreter' to indicate the type
            of the executable for the language.
        interface_library (list): Name of the library containing the yggdrasil
            interface for the target language.
        interface_directories (list): Directories containing code in the
            interface library for the target language.
        interface_dependencies (list): List of names of libraries that are
            required to use the interface on the current platform. This dosn't
            include libraries required by specific communication types which are
            described by supported_comm_options.
        supported_comms (list): Name of comms supported in the target language.
        supported_comm_options (dict): Options for the supported comms like the
            platforms they are available on and the external libraries required
            to use them.
        external_libraries (dict): Information on external libraries required
            for running models in the target language using yggdrasil.
        internal_libraries (dict): Information on internal libraries required
            for running models in the target language using yggdrasil.
        function_param (dict): Options specifying how different operations
            would be encoded in the target language (e.g. if statements, for
            loops, while loops).
        version_flags (list): Flags that should be called with the language
            executable to determine the version of the compiler/interpreter.

    Attributes:
        args (list): Argument(s) for running the model on the command line.
        model_file (str): Full path to the compiled model executable.
        model_args (list): Runtime arguments for running the model on the command
            line.
        overwrite (bool): If True, any existing compilation products will be
            overwritten by compilation and cleaned up following the run.
            Otherwise, existing products will be used and will remain after
            the run.
        products (list): File created by running the model. This includes
            any wrappers that are created or compile executables/object
            files.
        process (:class:`yggdrasil.tools.YggPopen`): Process used to run
            the model.
        is_server (bool): If True, the model is assumed to be a server and an
            instance of :class:`yggdrasil.drivers.ServerDriver` is
            started.
        client_of (list): The names of server models that this model is a
            client of.
        with_strace (bool): If True, the command is run with strace or dtrace.
        strace_flags (list): Flags to pass to strace/dtrace.
        with_valgrind (bool): If True, the command is run with valgrind.
        valgrind_flags (list): Flags to pass to valgrind.
        model_index (int): Index of model in list of models being run.

    Raises:
        RuntimeError: If both with_strace and with_valgrind are True.

    """

    _schema_type = 'model'
    _schema_subtype_key = 'language'
    _schema_required = ['name', 'language', 'args', 'working_dir']
    _schema_properties = {
        'name': {'type': 'string'},
        'language': {'type': 'string', 'default': 'executable',
                     'description': ('The programming language that the model '
                                     'is written in.')},
        'args': {'type': 'array',
                 'items': {'type': 'string'}},
        'inputs': {'type': 'array', 'default': [],
                   'items': {'$ref': '#/definitions/comm'},
                   'description': 'Model inputs described as comm objects.'},
        'outputs': {'type': 'array', 'default': [],
                    'items': {'$ref': '#/definitions/comm'},
                    'description': 'Model outputs described as comm objects.'},
        'products': {'type': 'array', 'default': [],
                     'items': {'type': 'string'}},
        'working_dir': {'type': 'string'},
        'overwrite': {'type': 'boolean', 'default': True},
        'preserve_cache': {'type': 'boolean', 'default': False},
        'is_server': {'type': 'boolean', 'default': False},
        'client_of': {'type': 'array', 'items': {'type': 'string'},
                      'default': []},
        'with_strace': {'type': 'boolean', 'default': False},
        'strace_flags': {'type': 'array', 'default': [],
                         'items': {'type': 'string'}},
        'with_valgrind': {'type': 'boolean', 'default': False},
        'valgrind_flags': {'type': 'array', 'default': ['--leak-check=full'],  # '-v'
                           'items': {'type': 'string'}}}
    _schema_excluded_from_class = ['name', 'language', 'args',
                                   'inputs', 'outputs', 'working_dir']
    _schema_excluded_from_class_validation = ['inputs', 'outputs']
    
    language = None
    language_ext = None
    language_aliases = []
    base_languages = []
    executable_type = None
    interface_library = None
    interface_directories = []
    interface_dependencies = []
    supported_comms = []
    supported_comm_options = {}
    external_libraries = {}
    internal_libraries = {}
    function_param = None
    version_flags = ['--version']

    def __init__(self, name, args, model_index=0, **kwargs):
        super(ModelDriver, self).__init__(name, **kwargs)
        # Setup process things
        self.model_process = None
        self.queue = Queue()
        self.queue_thread = None
        self.event_process_kill_called = Event()
        self.event_process_kill_complete = Event()
        # Strace/valgrind
        if self.with_strace and self.with_valgrind:
            raise RuntimeError("Trying to run with strace and valgrind.")
        if (((self.with_strace or self.with_valgrind)
             and platform._is_win)):  # pragma: windows
            raise RuntimeError("strace/valgrind options invalid on windows.")
        self.model_index = model_index
        self.env_copy = ['LANG', 'PATH', 'USER']
        self._exit_line = b'EXIT'
        # print(os.environ.keys())
        for k in self.env_copy:
            if k in os.environ:
                self.env[k] = os.environ[k]
        if not self.is_installed():
            raise RuntimeError("%s is not installed" % self.language)
        # Parse arguments
        self.debug(str(args))
        self.raw_model_file = None
        self.model_file = None
        self.model_args = []
        self.model_dir = None
        self.products = []
        self.args = args
        self.parse_arguments(args)
        assert(self.model_file is not None)
        # Remove products
        if self.overwrite:
            self.remove_products()
        # Write wrapper
        self.products += self.write_wrappers()

    @staticmethod
    def before_registration(cls):
        r"""Operations that should be performed to modify class attributes prior
        to registration including things like platform dependent properties and
        checking environment variables for default settings.
        """
        Driver.before_registration(cls)
        cls._language = cls.language
        cls._language_aliases = cls.language_aliases
        if (((cls.language_ext is not None)
             and (not isinstance(cls.language_ext, (list, tuple))))):
            cls.language_ext = [cls.language_ext]
            
    @staticmethod
    def after_registration(cls):
        r"""Operations that should be preformed to modify class attributes after
        registration."""
        if (not cls.is_configured()):
            update_language_config(cls)
        
    def parse_arguments(self, args, default_model_dir=None):
        r"""Sort model arguments to determine which one is the executable
        and which ones are arguments.

        Args:
            args (list): List of arguments provided.
            default_model_dir (str, optional): Path to directory that should be
                used to normalize the model file path if it is not absolute.
                Defaults to None and is set to the working_dir.

        """
        if isinstance(args, backwards.string_types):
            args = args.split()
        assert(isinstance(args, list))
        if default_model_dir is None:
            default_model_dir = self.working_dir
        self.raw_model_file = backwards.as_str(args[0])
        self.model_file = self.raw_model_file
        self.model_args = []
        for a in args[1:]:
            try:
                self.model_args.append(backwards.as_str(a))
            except TypeError:
                self.model_args.append(str(a))
        if (self.language != 'executable') and (not os.path.isabs(self.model_file)):
            model_file = os.path.normpath(os.path.join(default_model_dir,
                                                       self.model_file))
            self.model_file = model_file
        self.model_dir = os.path.dirname(self.model_file)
        self.debug("model_file = '%s', model_dir = '%s', model_args = '%s'",
                   self.model_file, self.model_dir, self.model_args)

    def write_wrappers(self, **kwargs):
        r"""Write any wrappers needed to compile and/or run a model.

        Args:
            **kwargs: Keyword arguments are ignored (only included to
               allow cascade from child classes).

        Returns:
            list: Full paths to any created wrappers.

        """
        return []
        
    def model_command(self):
        r"""Return the command that should be used to run the model.

        Returns:
            list: Any commands/arguments needed to run the model from the
                command line.

        """
        return [self.model_file] + self.model_args

    @classmethod
    def language_executable(cls):
        r"""Command required to compile/run a model written in this language
        from the command line.

        Returns:
            str: Name of (or path to) compiler/interpreter executable required
                to run the compiler/interpreter from the command line.

        """
        raise NotImplementedError("language_executable not implemented for '%s'"
                                  % cls.language)
        
    @classmethod
    def executable_command(cls, args, unused_kwargs=None, **kwargs):
        r"""Compose a command for running a program using the exectuable for
        this language (compiler/interpreter) with the provided arguments.

        Args:
            args (list): The program that returned command should run and any
                arguments that should be provided to it.
            unused_kwargs (dict, optional): Existing dictionary that unused
                keyword arguments should be added to. Defaults to None and is
                ignored.
            **kwargs: Additional keyword arguments are ignored.

        Returns:
            list: Arguments composing the command required to run the program
                from the command line using the executable for this language.

        """
        if isinstance(unused_kwargs, dict):
            unused_kwargs.update(kwargs)
        raise NotImplementedError("executable_command not implemented for '%s'"
                                  % cls.language)

    @classmethod
    def run_executable(cls, args, return_process=False, **kwargs):
        r"""Run a program using the executable for this language and the
        provided arguments.

        Args:
            args (list): The program that should be run and any arguments
                that should be provided to it.
            return_process (bool, optional): If True, the process class is
                returned without checking the process output. If False,
                communicate is called on the process and the output is parsed
                for errors. Defaults to False.
            **kwargs: Additional keyword arguments are passed to
                cls.executable_command and tools.popen_nobuffer.

        Returns:
            str: Output to stdout from the run command if return_process is
                False, the process if return_process is True.
        
        Raises:
            RuntimeError: If the language is not installed.
            RuntimeError: If there is an error when running the command.

        """
        # if not cls.is_language_installed():
        #     raise RuntimeError("Language '%s' is not installed."
        #                        % cls.language)
        unused_kwargs = {}
        cmd = cls.executable_command(args, unused_kwargs=unused_kwargs, **kwargs)
        try:
            # Add default keyword arguments
            if 'working_dir' in unused_kwargs:
                unused_kwargs.setdefault('cwd', unused_kwargs.pop('working_dir'))
            unused_kwargs.setdefault('shell', platform._is_win)
            # Call command
            logging.info("Running '%s' from %s"
                         % (' '.join(cmd), unused_kwargs.get('cwd', os.getcwd())))
            logging.debug("Process keyword arguments:\n%s\n",
                          '    ' + pformat(unused_kwargs).replace('\n', '\n    '))
            proc = tools.popen_nobuffer(cmd, **unused_kwargs)
            if return_process:
                return proc
            out, err = proc.communicate()
            if proc.returncode != 0:
                logging.error(out)
                raise RuntimeError("Command '%s' failed with code %d."
                                   % (' '.join(cmd), proc.returncode))
            out = backwards.as_str(out)
            logging.debug('%s\n%s' % (' '.join(cmd), out))
            return out
        except (subprocess.CalledProcessError, OSError) as e:
            raise RuntimeError("Could not call command '%s': %s"
                               % (' '.join(cmd), e))
        
    def run_model(self, **kwargs):
        r"""Run the model. Unless overridden, the model will be run using
        run_executable.

        Args:
            **kwargs: Keyword arguments are passed to run_executable.

        """
        env = self.set_env()
        pre_args = []
        if self.with_strace:
            if platform._is_linux:
                pre_cmd = 'strace'
            elif platform._is_mac:
                pre_cmd = 'dtrace'
            pre_args += [pre_cmd] + self.strace_flags
        elif self.with_valgrind:
            pre_args += ['valgrind'] + self.valgrind_flags
        command = pre_args + self.model_command()
        self.debug('Working directory: %s', self.working_dir)
        self.debug('Command: %s', ' '.join(command))
        self.debug('Environment Variables:\n%s', self.pprint(env, block_indent=1))
        # Update keywords
        # NOTE: Setting forward_signals to False allows faster debugging
        # but should not be used in deployment for cases where models are not
        # running locally.
        default_kwargs = dict(env=env, working_dir=self.working_dir,
                              forward_signals=False,
                              shell=platform._is_win)
        for k, v in default_kwargs.items():
            kwargs.setdefault(k, v)
        return self.run_executable(command, return_process=True, **kwargs)
        
    @classmethod
    def language_version(cls, **kwargs):
        r"""Determine the version of this language.

        Args:
            **kwargs: Keyword arguments are passed to cls.run_executable.

        Returns:
            str: Version of compiler/interpreter for this language.

        """
        return cls.run_executable(cls.version_flags, **kwargs)

    @classmethod
    def is_installed(cls):
        r"""Determine if this model driver is installed on the current
        machine.

        Returns:
            bool: Truth of if this model driver can be run on the current
                machine.

        """
        return (cls.is_language_installed() and cls.are_dependencies_installed()
                and cls.is_comm_installed() and cls.is_configured())

    @classmethod
    def are_dependencies_installed(cls):
        r"""Determine if the dependencies are installed for the interface (not
        including dependencies needed by a particular communication type).

        Returns:
            bool: True if the dependencies are installed. False otherwise.

        """
        out = (cls.language is not None)
        for x in cls.base_languages:
            if not out:
                break
            out = import_component('model', x).are_dependencies_installed()
        if out:
            for x in cls.interface_dependencies:
                if not out:
                    break
                out = cls.is_library_installed(x)
        return out

    @classmethod
    def is_language_installed(cls):
        r"""Determine if the interpreter/compiler for the associated programming
        language is installed.

        Returns:
            bool: True if the language interpreter/compiler is installed.

        """
        out = False
        if cls.language is not None:
            out = (tools.which(cls.language_executable()) is not None)
        for x in cls.base_languages:
            if not out:
                break
            out = import_component('model', x).is_language_installed()
        return out

    @classmethod
    def is_library_installed(cls, lib, **kwargs):
        r"""Determine if a dependency is installed.

        Args:
            lib (str): Name of the library that should be checked.
            **kwargs: Additional keyword arguments are ignored.

        Returns:
            bool: True if the library is installed, False otherwise.

        """
        raise NotImplementedError("Method is_library_installed missing for '%s'"
                                  % cls.language)

    @classmethod
    def is_configured(cls):
        r"""Determine if the appropriate configuration has been performed (e.g.
        installation of supporting libraries etc.)

        Returns:
            bool: True if the language has been configured.

        """
        # Check for section & diable
        disable_flag = ygg_cfg.get(cls.language, 'disable', 'false').lower()
        out = (ygg_cfg.has_section(cls.language) and (disable_flag != 'true'))
        # Check for commtypes
        if out and (len(cls.base_languages) == 0):
            out = (ygg_cfg.get(cls.language, 'commtypes', None) is not None)
        # Base languages
        for x in cls.base_languages:
            if not out:
                break
            out = import_component('model', x).is_configured()
        return out

    @classmethod
    def is_comm_installed(cls, commtype=None, skip_config=False, **kwargs):
        r"""Determine if a comm is installed for the associated programming
        language.

        Args:
            commtype (str, optional): If provided, this method will only test
                for installation of the specified communication type. Defaults
                to None and will check for any installed comm.
            skip_config (bool, optional): If True, the config list of comms
                installed for this language will not be used to determine if
                the comm is installed and the class attribute
                supported_comm_options will be processed. Defaults to False and
                config options are used in order to improve performance after
                initial configuration.
            platforms (list, optional): Platforms on which the comm can be
                installed. Defaults to None and is ignored unless there is a
                value for the commtype in supported_comm_options. This
                keyword argument is ignored if skip_config is False.
            libraries (list, optional): External libraries that are required
                by the specified commtype. Defaults to None and is ignored
                unless there is a value for the commtype in supported_comm_options.
                This keyword argument is ignored if skip_config is False.
            **kwargs: Additional keyword arguments are passed to either
                is_comm_installed for the base languages, supported languages,
                or is_library_installed as appropriate.

        Returns:
            bool: True if a comm is installed for this language.

        """
        # If there are base_languages for this language, use that language's
        # driver to check for comm installation.
        if len(cls.base_languages) > 0:
            out = True
            for x in cls.base_languages:
                if not out:
                    break
                out = import_component('model', x).is_comm_installed(
                    commtype=commtype, skip_config=skip_config, **kwargs)
            return out
        # Check for installation based on config option
        if not skip_config:
            installed_comms = ygg_cfg.get(cls.language, 'commtypes', [])
            if commtype is None:
                return (len(installed_comms) > 0)
            else:
                return (commtype in installed_comms)
        # Check for any comm
        if commtype is None:
            for c in tools.get_supported_comm():
                if cls.is_comm_installed(commtype=c, **kwargs):
                    return True
            return False
        # Check that comm is explicitly supported
        if commtype not in cls.supported_comms:
            return False
        # Set & pop keywords
        for k, v in cls.supported_comm_options.get(commtype, {}).items():
            if kwargs.get(k, None) is None:
                kwargs[k] = v
        platforms = kwargs.pop('platforms', None)
        libraries = kwargs.pop('libraries', [])
        # Check platforms
        if (platforms is not None) and (platform._platform not in platforms):
            return False
        # Check libraries
        if (libraries is not None):
            for lib in libraries:
                if not cls.is_library_installed(lib, **kwargs):
                    return False
        return True

    @classmethod
    def configure(cls, cfg):
        r"""Add configuration options for this language.

        Args:
            cfg (CisConfigParser): Config class that options should be set for.
        
        Returns:
            list: Section, option, description tuples for options that could not
                be set.

        """
        # Base languages
        # TODO: Verify that this dosn't cause issues
        for x in cls.base_languages:
            x_drv = import_component('model', x)
            if not x_drv.is_configured():
                x_drv.configure()
        # Section and executable
        if (cls.language is not None) and (not cfg.has_section(cls.language)):
            cfg.add_section(cls.language)
        # Locate executable
        if (((not cls.is_language_installed())
             and (cls.executable_type is not None))):  # pragma: debug
            fpath = locate_file(cls.language_executable())
            if fpath:
                cfg.set(cls.language, cls.executable_type, fpath)
        # Only do additional configuration if no base languages
        out = []
        if not cls.base_languages:
            # Configure libraries
            out += cls.configure_libraries(cfg)
            # Installed comms
            comms = []
            for c in tools.get_supported_comm():
                if cls.is_comm_installed(commtype=c, cfg=cfg, skip_config=True):
                    comms.append(c)
            cfg.set(cls.language, 'commtypes', str(comms))
        return out

    @classmethod
    def configure_libraries(cls, cfg):
        r"""Add configuration options for external libraries in this language.

        Args:
            cfg (CisConfigParser): Config class that options should be set for.
        
        Returns:
            list: Section, option, description tuples for options that could not
                be set.

        """
        return []
        
    def set_env(self):
        r"""Get environment variables that should be set for the model process.

        Returns:
            dict: Environment variables for the model process.

        """
        env = copy.deepcopy(self.env)
        env.update(os.environ)
        env['YGG_SUBPROCESS'] = "True"
        env['YGG_MODEL_INDEX'] = str(self.model_index)
        return env

    def before_start(self, no_queue_thread=False, **kwargs):
        r"""Actions to perform before the run starts.

        Args:
            no_queue_thread (bool, optional): If True, the queue_thread is not
                created/started. Defaults to False.
            **kwargs: Keyword arguments are pased to run_model.

        """
        self.model_process = self.run_model(**kwargs)
        # Start thread to queue output
        if not no_queue_thread:
            self.queue_thread = tools.YggThreadLoop(
                target=self.enqueue_output_loop,
                name=self.name + '.EnqueueLoop')
            self.queue_thread.start()

    def enqueue_output_loop(self):
        r"""Keep passing lines to queue."""
        # if self.model_process_complete:
        #     self.debug("Process complete")
        #     self.queue_thread.set_break_flag()
        #     self.queue.put(self._exit_line)
        #     return
        try:
            line = self.model_process.stdout.readline()
        except BaseException as e:  # pragma: debug
            print(e)
            line = ""
        if len(line) == 0:
            # self.info("%s: Empty line from stdout" % self.name)
            self.queue_thread.set_break_flag()
            self.queue.put(self._exit_line)
            self.debug("End of model output")
            try:
                self.model_process.stdout.close()
            except BaseException:  # pragma: debug
                pass
        else:
            try:
                self.queue.put(line.decode('utf-8'))
            except BaseException as e:  # pragma: debug
                warnings.warn("Error in printing output: %s" % e)

    def before_loop(self):
        r"""Actions before loop."""
        self.debug('Running %s from %s with cwd %s and env %s',
                   self.model_command(), os.getcwd(), self.working_dir,
                   pformat(self.env))

    def run_loop(self):
        r"""Loop to check if model is still running and forward output."""
        # Continue reading until there is not any output
        try:
            line = self.queue.get_nowait()
        except Empty:
            # if self.queue_thread.was_break:
            #     self.debug("No more output")
            #     self.set_break_flag()
            # This sleep is necessary to allow changes in queue without lock
            self.sleep()
            return
        else:
            if (line == self._exit_line):
                self.debug("No more output")
                self.set_break_flag()
            else:
                self.print_encoded(line, end="")
                sys.stdout.flush()

    def after_loop(self):
        r"""Actions to perform after run_loop has finished. Mainly checking
        if there was an error and then handling it."""
        self.debug('')
        if self.queue_thread is not None:
            self.queue_thread.join(self.sleeptime)
            if self.queue_thread.is_alive():
                self.debug("Queue thread still alive")
                # Loop was broken from outside, kill the queueing thread
                self.kill_process()
                # self.queue_thread.set_break_flag()
                # try:
                #     self.model_process.stdout.close()
                # except BaseException:  # pragma: debug
                #     self.error("Close during concurrent operation")
                return
        self.wait_process(self.timeout, key_suffix='.after_loop')
        self.kill_process()

    @property
    def model_process_complete(self):
        r"""bool: Has the process finished or not. Returns True if the process
        has not started."""
        if self.model_process is None:  # pragma: debug
            return True
        return (self.model_process.poll() is not None)

    def wait_process(self, timeout=None, key=None, key_suffix=None):
        r"""Wait for some amount of time for the process to finish.

        Args:
            timeout (float, optional): Time (in seconds) that should be waited.
                Defaults to None and is infinite.
            key (str, optional): Key that should be used to register the timeout.
                Defaults to None and set based on the stack trace.

        Returns:
            bool: True if the process completed. False otherwise.

        """
        if not self.was_started:  # pragma: debug
            return True
        T = self.start_timeout(timeout, key_level=1, key=key, key_suffix=key_suffix)
        while ((not T.is_out) and (not self.model_process_complete)):  # pragma: debug
            self.sleep()
        self.stop_timeout(key_level=1, key=key, key_suffix=key_suffix)
        return self.model_process_complete

    def kill_process(self):
        r"""Kill the process running the model, checking return code."""
        if not self.was_started:  # pragma: debug
            self.debug('Process was never started.')
            self.set_break_flag()
            self.event_process_kill_called.set()
            self.event_process_kill_complete.set()
        if self.event_process_kill_called.is_set():  # pragma: debug
            self.debug('Process has already been killed.')
            return
        self.event_process_kill_called.set()
        with self.lock:
            self.debug('')
            if not self.model_process_complete:  # pragma: debug
                self.error("Process is still running. Killing it.")
                try:
                    self.model_process.kill()
                    self.debug("Waiting %f s for process to be killed",
                               self.timeout)
                    self.wait_process(self.timeout, key_suffix='.kill_process')
                except BaseException:  # pragma: debug
                    self.exception("Error killing model process")
            assert(self.model_process_complete)
            if self.model_process.returncode != 0:
                self.error("return code of %s indicates model error.",
                           str(self.model_process.returncode))
            self.event_process_kill_complete.set()
            if self.queue_thread is not None:
                if not self.was_break:  # pragma: debug
                    # Wait for messages to be printed
                    self.debug("Waiting for queue_thread to finish up.")
                    self.queue_thread.wait(self.timeout)
                if self.queue_thread.is_alive():  # pragma: debug
                    self.debug("Setting break flag for queue_thread to finish up.")
                    self.queue_thread.set_break_flag()
                    self.queue_thread.wait(self.timeout)
                    try:
                        self.model_process.stdout.close()
                        self.queue_thread.wait(self.timeout)
                    except BaseException:  # pragma: debug
                        self.exception("Closed during concurrent action")
                    if self.queue_thread.is_alive():  # pragma: debug
                        self.error("Queue thread was not terminated.")

    def graceful_stop(self):
        r"""Gracefully stop the driver."""
        self.debug('')
        self.wait_process(self.timeout, key_suffix='.graceful_stop')
        super(ModelDriver, self).graceful_stop()

    def cleanup(self):
        r"""Remove compile executable."""
        if self.overwrite:
            self.remove_products()
        super(ModelDriver, self).cleanup()
        
    def remove_products(self):
        r"""Delete products produced during the process of running the model."""
        for p in self.products:
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.isfile(p):
                T = self.start_timeout()
                while ((not T.is_out) and os.path.isfile(p)):
                    try:
                        os.remove(p)
                    except BaseException:  # pragma: debug
                        if os.path.isfile(p):
                            self.sleep()
                        if T.is_out:
                            raise
                self.stop_timeout()
                if os.path.isfile(p):  # pragma: debug
                    raise RuntimeError("Failed to remove product: %s" % p)

    # def do_terminate(self):
    #     r"""Terminate the process running the model."""
    #     self.debug('')
    #     self.kill_process()
    #     super(ModelDriver, self).do_terminate()
                
    # Methods for automated model wrapping
    @classmethod
    def write_if_block(cls, cond, block_contents):
        r"""Return the lines required to complete a conditional block.

        Args:
            cond (str): Conditional that should determine block execution.
            block_contents (list): Lines of code that should be executed inside
                the block.

        Returns:
            list: Lines of code performing conditional execution of a block.

        """
        if cls.function_param is None:
            raise NotImplementedError("function_param attribute not set for"
                                      "language '%s'" % cls.language)
        out = []
        # Opening for statement line
        out.append(cls.function_param['if_begin'].format(cond=cond))
        # Indent loop contents
        if not isinstance(block_contents, (list, tuple)):
            block_contents = [block_contents]
        for x in block_contents:
            out.append(cls.function_param['indent'] + x)
        # Close block
        out.append(cls.function_param.get('if_end',
                                          cls.function_param['block_end']))
        return out
                   
    @classmethod
    def write_for_loop(cls, iter_var, iter_begin, iter_end, loop_contents):
        r"""Return the lines required to complete a for loop.

        Args:
            iter_var (str): Name of variable that iterator should use.
            iter_begin (int): Beginning of iteration.
            iter_end (int): End of iteration.
            loop_contents (list): Lines of code that should be executed inside
                the loop.

        Returns:
            list: Lines of code performing a loop.

        """
        if cls.function_param is None:
            raise NotImplementedError("function_param attribute not set for"
                                      "language '%s'" % cls.language)
        out = []
        # Opening for statement line
        out.append(cls.function_param['for_begin'].format(
            iter_var=iter_var, iter_begin=iter_begin, iter_end=iter_end))
        # Indent loop contents
        if not isinstance(loop_contents, (list, tuple)):
            loop_contents = [loop_contents]
        for x in loop_contents:
            out.append(cls.function_param['indent'] + x)
        # Close block
        out.append(cls.function_param.get('for_end',
                                          cls.function_param['block_end']))
        return out

    @classmethod
    def write_while_loop(cls, cond, loop_contents):
        r"""Return the lines required to complete a for loop.

        Args:
            cond (str): Conditional that should determine loop execution.
            loop_contents (list): Lines of code that should be executed inside
                the loop.

        Returns:
            list: Lines of code performing a loop.

        """
        if cls.function_param is None:
            raise NotImplementedError("function_param attribute not set for"
                                      "language '%s'" % cls.language)
        out = []
        # Opening for statement line
        out.append(cls.function_param['while_begin'].format(cond=cond))
        # Indent loop contents
        if not isinstance(loop_contents, (list, tuple)):
            loop_contents = [loop_contents]
        for x in loop_contents:
            out.append(cls.function_param['indent'] + x)
        # Close block
        out.append(cls.function_param.get('while_end',
                                          cls.function_param['block_end']))
        return out

    @classmethod
    def write_try_except(cls, try_contents, except_contents, error_var='e',
                         error_type=None):
        r"""Return the lines required to complete a try/except block.

        Args:
            try_contents (list): Lines of code that should be executed inside
                the try block.
            except_contents (list): Lines of code that should be executed inside
                the except block.
            error_var (str, optional): Name of variable where the caught error
                should be stored. Defaults to 'e'.
            error_type (str, optional): Name of error type that should be caught.
                If not provided, defaults to None and will be set based on the
                class function_param entry for 'try_error_type'.

        Returns:
            Lines of code perfoming a try/except block.

        """
        if cls.function_param is None:
            raise NotImplementedError("function_param attribute not set for"
                                      "language '%s'" % cls.language)
        if error_type is None:
            error_type = cls.function_param.get('try_error_type', None)
        out = []
        # Try block contents
        if not isinstance(try_contents, (list, tuple)):
            try_contents = [try_contents]
        out.append(cls.function_param['try_begin'])
        for x in try_contents:
            out.append(cls.function_param['indent'] + x)
        # Except block contents
        if not isinstance(except_contents, (list, tuple)):
            except_contents = [except_contents]
        out.append(cls.function_param['try_except'].format(error_var=error_var,
                                                           error_type=error_type))
        for x in except_contents:
            out.append(cls.function_param['indent'] + x)
        # Close block
        out.append(cls.function_param.get('try_end',
                                          cls.function_param['block_end']))
        return out
