import pandas
import copy
import numpy as np
import warnings
from yggdrasil import backwards, platform, serialize
from yggdrasil.metaschema.datatypes.ArrayMetaschemaType import (
    OneDArrayMetaschemaType)
from yggdrasil.serialize.AsciiTableSerialize import AsciiTableSerialize


class PandasSerialize(AsciiTableSerialize):
    r"""Class for serializing/deserializing Pandas data frames.

    Args:
        dont_write_header (bool, optional): If True, headers will not be added
            to serialized tables. Defaults to False.

    """

    _seritype = 'pandas'
    _schema_subtype_description = ('Serializes tables using the pandas package.')
    _schema_properties = {'dont_write_header': {'type': 'boolean', 'default': False}}
    write_header_once = False
    default_read_meth = 'read'

    @property
    def empty_msg(self):
        r"""obj: Object indicating empty message."""
        return pandas.DataFrame()

    def apply_field_names(self, frame):
        r"""Apply field names as columns to a frame, first checking for a mapping.
        If there is a direct mapping, the columns are reordered to match the order
        of the field names. If there is not an overlap in the field names and
        columns, a one-to-one mapping is assumed, but a warning is issued. If there
        is a partial overlap, an error is raised.

        Args:
            frame (pandas.DataFrame): Frame to apply field names to as columns.

        Returns:
            pandas.DataFrame: Frame with updated field names.

        Raises:
            RuntimeError: If there is a partial overlap between the field names
                and columns.

        """
        field_names = self.get_field_names()
        if field_names is None:
            return frame
        cols = frame.columns.tolist()
        if len(field_names) != len(cols):
            raise RuntimeError(("Number of field names (%d) doesn't match "
                                + "number of columns in data frame (%d).")
                               % (len(field_names), len(cols)))
        # Check for missing fields
        fmiss = []
        for f in field_names:
            if f not in cols:
                fmiss.append(f)
        if fmiss:
            if len(fmiss) == len(field_names):
                warnings.warn("Assuming direct mapping of field names to columns. "
                              + "This may not be correct.")
                frame.columns = field_names
            else:
                # Partial overlap
                raise RuntimeError("%d fields missing from frame: %s"
                                   % (len(fmiss), str(fmiss)))
        else:
            # Reorder columns
            frame = frame[field_names]
        return frame

    def func_serialize(self, args):
        r"""Serialize a message.

        Args:
            args (obj): Python object to be serialized.

        Returns:
            bytes, str: Serialized message.

        """
        if not isinstance(args, pandas.DataFrame):
            raise TypeError(("Pandas DataFrame required. Invalid type "
                             + "of '%s' provided.") % type(args))
        fd = backwards.StringIO()
        if backwards.PY2:  # pragma: Python 2
            args_ = args
        else:  # pragma: Python 3
            # For Python 3 and higher, bytes need to be encoded
            args_ = copy.deepcopy(args)
            for c in args.columns:
                if isinstance(args_[c][0], backwards.bytes_type):
                    args_[c] = args_[c].apply(lambda s: s.decode('utf-8'))
        args_ = self.apply_field_names(args_)
        args_.to_csv(fd, index=False,
                     # Not in pandas <0.24
                     # line_terminator=backwards.as_str(self.newline),
                     sep=backwards.as_str(self.delimiter),
                     mode='wb', encoding='utf8',
                     header=(not self.dont_write_header))
        if self.write_header_once:
            self.dont_write_header = True
        out = fd.getvalue()
        fd.close()
        # Required to change out \r\n for \n on windows
        out = out.replace(
            backwards.match_stype(out, platform._newline),
            backwards.match_stype(out, self.newline))
        return backwards.as_bytes(out)

    def func_deserialize(self, msg):
        r"""Deserialize a message.

        Args:
            msg (str, bytes): Message to be deserialized.

        Returns:
            obj: Deserialized Python object.

        """
        fd = backwards.BytesIO(msg)
        out = pandas.read_csv(fd,
                              sep=backwards.as_str(self.delimiter),
                              encoding='utf8')
        fd.close()
        if not backwards.PY2:
            # For Python 3 and higher, make sure strings are bytes
            for c, d in zip(out.columns, out.dtypes):
                if d == object:
                    out[c] = out[c].apply(lambda s: s.encode('utf-8'))
        # On windows, long != longlong and longlong requires special cformat
        # For now, long will be used to preserve the use of %ld to match long
        if platform._is_win:  # pragma: windows
            if np.dtype('longlong').itemsize == 8:
                new_dtypes = dict()
                for c, d in zip(out.columns, out.dtypes):
                    if d == np.dtype('longlong'):
                        new_dtypes[c] = np.int32
                    else:
                        new_dtypes[c] = d
                out = out.astype(new_dtypes, copy=False)
        # Reorder if necessary
        out = self.apply_field_names(out)
        if self.field_names is None:
            self.field_names = out.columns.tolist()
        # for c, d in zip(out.columns, out.dtypes):
        #     if d == object:
        #         out[c] = out[c].apply(lambda s: s.strip())
        if not self._initialized:
            typedef = {'type': 'array', 'items': []}
            np_out = serialize.pandas2numpy(out)
            for n in self.get_field_names():
                typedef['items'].append(OneDArrayMetaschemaType.encode_type(
                    np_out[n], title=n))
            self.update_serializer(extract=True, **typedef)
        return out

    @classmethod
    def send_converter(cls, obj):
        r"""Performs conversion from a limited set of objects to a Pandas data
        frame for sending to a file via PandasFileComm. Currently supports
        converting from structured numpy arrays, lists/tuples of numpy arrays,
        and dictionaries.

        Args:
            obj (object): Object to convert.

        Returns:
            pandas.DataFrame: Converted data frame (or unmodified input if
                conversion could not be completed.

        """
        if isinstance(obj, (list, tuple)):
            obj = serialize.list2pandas(obj)
        elif isinstance(obj, np.ndarray):
            obj = serialize.numpy2pandas(obj)
        elif isinstance(obj, dict):
            obj = serialize.dict2pandas(obj)
        return obj

    @classmethod
    def recv_converter(cls, obj):
        r"""Performs conversion to a limited set of objects from a Pandas data
        frame for receiving from a file via PandasFileComm. Currently supports
        converting to lists/tuples of numpy arrays.

        Args:
            obj (pandas.DataFrame): Data frame to convert.

        Returns:
            list: pandas.DataFrame: Converted data frame (or unmodified input if
                conversion could not be completed.

        """
        return serialize.pandas2list(obj)

    @classmethod
    def object2dict(cls, obj):
        r"""Convert a message object into a dictionary.

        Args:
            obj (object): Object that would be serialized by this class and
                should be returned in a dictionary form.

        Returns:
            dict: Dictionary version of the provided object.

        """
        return serialize.pandas2dict(obj)

    @classmethod
    def object2array(cls, obj):
        r"""Convert a message object into an array.

        Args:
            obj (object): Object that would be serialized by this class and
                should be returned in an array form.

        Returns:
            np.array: Array version of the provided object.

        """
        return serialize.pandas2numpy(obj)

    @classmethod
    def concatenate(cls, objects):
        r"""Concatenate objects to get object that would be recieved if
        the concatenated serialization were deserialized.

        Args:
            objects (list): Objects to be concatenated.

        Returns:
            list: Set of objects that results from concatenating those provided.

        """
        if len(objects) == 0:
            return []
        if isinstance(objects[0], list):
            return super(PandasSerialize, cls).concatenate(objects, as_array=True)
        else:
            return [pandas.concat(objects, ignore_index=True)]
        
    @classmethod
    def get_testing_options(cls, not_as_frames=False, no_names=False, **kwargs):
        r"""Method to return a dictionary of testing options for this class.

        Args:
            not_as_frames (bool, optional): If True, the returned example
                includes data that is not in a pandas data frame. Defaults to
                False.
            no_names (bool, optional): If True, an example is returned where the
                names are not provided to the deserializer. Defaults to False.

        Returns:
            dict: Dictionary of variables to use for testing.

        """
        out = super(PandasSerialize, cls).get_testing_options(as_array=True)
        for k in ['as_array']:  # , 'format_str']:
            if k in out['kwargs']:
                del out['kwargs'][k]
        out['extra_kwargs'] = {}
        out['empty'] = pandas.DataFrame()
        if no_names:
            del out['kwargs']['field_names']
            field_names = None
            header_line = b'f0\tf1\tf2\n'
        else:
            field_names = [backwards.as_str(x) for
                           x in out['kwargs']['field_names']]
            header_line = b'name\tcount\tsize\n'
        out['contents'] = (header_line
                           + b'one\t1\t1.0\n'
                           + b'two\t2\t2.0\n'
                           + b'three\t3\t3.0\n'
                           + b'one\t1\t1.0\n'
                           + b'two\t2\t2.0\n'
                           + b'three\t3\t3.0\n')
        if not not_as_frames:
            out['objects'] = [serialize.list2pandas(x, names=field_names)
                              for x in out['objects']]
        out['kwargs'].update(out['typedef'])
        return out

    def serialize_header(self):
        r"""Return the serialized header information that should be prepended
        to files serialized using this class.

        Returns:
            bytes: Header string that should be written to the file.

        """
        self.dont_write_header = False
        self.write_header_once = True

    def deserialize_header(self, fd):
        r"""Deserialize the header information from the file and update the
        serializer.

        Args:
            fd (file): File containing header.

        """
        pass
