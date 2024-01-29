import OpenEXR
from dataclasses import dataclass
from typing import Any
from array import array


@dataclass
class OpenEXRWrapper:
    '''Wrapper for OpenEXR.InputFile

    Args:
     - inputfile: The OpenEXR.InputFile object
     - channel_names: List of names for accessing channels
     - resolution: Resolution of the image (height,width)
    '''
    inputfile: OpenEXR.InputFile
    channel_names: list
    resolution: tuple

    @property
    def header(self) -> dict:
        '''Get the header of the EXR file
        '''
        return self.inputfile.header()



@dataclass
class OpenEXRReader():
    '''Read OpenEXR images generated by BAT

    Args:
     - filepath: Path to the exr file
     - channel_string: String describing which channels to load
     - loader: Module to use to load the channel data (Values types will depend on the loader!)
     - resolution: Resolution of the image (height,width)
     - view_layer_name: Name of the ViewLayer used by BAT inside Blender

    Usage:
    with OpenEXRReader(PATH, CHSTR) as exr:
        ...
    
    The channel string (CHSTR) can contain the following codes:
     c: Class ID channel (Each pixel has a value that tells which class the pixel belongs to)
     i: Instance ID (Each pixel has a value that tells which instance the pixel belongs to.
        Instances are not unique if there are multiple classes! The Class ID + Instance ID combination is unique.)
     r: Red color channel for visualization purposes. (Pixel values are the product of the red component of the
        class color setup in BAT and the Instance ID)
     g: Green color channel for visualization purposes. (Pixel values are the product of the green component of the
        class color setup in BAT and the Instance ID)
     b: Blue color channel for visualization purposes. (Pixel values are the product of the blue component of the
        class color setup in BAT and the Instance ID)
     a: Alpha channel (Can be used for binary, background-foreground segmentation.)
     d: Depth channel (Pixel values contain the distance from the camera in meters)
     nx: The X component of the surface normals
     ny: The Y component of the surface normals
     nz: The Z component of the surface normals
     fx: The X components of the optical flow vector
     fy: fx: The X components of the optical flow vector

    (Others might also be possible, such as fz, nw etc., but those are not meaningful and will likely result in error)

    In order to load the red, green and blue image channels for example:
    with OpenEXRReader(PATH, 'rgb') as exr:
        r_channel = exr.r
        g_channel = exr.g
        b_channel = exr.b
        ...
    
    The channels referenced through the channel string can be accessed as attributes of the exr object.
    '''
    filepath: str
    channel_string: str
    loader: Any = None
    resolution: tuple = (1080,1920)
    view_layer_name: str = 'BAT_ViewLayer'


    def __post_init__(self):
        '''This will be called at the end of the __init__ method
        '''
        self.channels = {}
        self.two_char_expr_starts = 'nf'  # Collection of characters that start a two character expression

        # Parse channel string to know which channels to load
        self.channel_names, self.channel_keys = self._parse_channel_string(self.channel_string)


    def __enter__(self) -> OpenEXRWrapper:
        '''Defines what should be returned if the object is used in a with statement
        '''
        # Create the OpenEXR.InputFile object
        self.inputfile = OpenEXR.InputFile(self.filepath)
        # Load the required channels (They will be stored in self.channels)
        self._load_channels(self.channel_names, self.channel_keys)

        # Create metaclass to dinamically add attributes to the OpenEXRWrapper class
        # The added attributes will be the loaded channels
        class OpenEXRMeta(type):
            def __new__(cls, name, bases, dct):
                for k,v in self.channels.items():
                    dct[k] = v
                x = super().__new__(cls, name, bases, dct)
                return x

        # Create an implementation of the OpenEXRWrapper using the metaclass
        class OpenExRWrapperIpl(OpenEXRWrapper,metaclass=OpenEXRMeta):
            pass 
        
        # Return an instance of this implementation
        return OpenExRWrapperIpl(self.inputfile, self.channel_keys, self.resolution)


    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        '''Defines what should happen when we leave the with statement
        '''
        self.inputfile.close()


    def _parse_channel_string(self, channel_string: str) -> tuple:
        '''Parse the channel string and return a tuple containing the list of channel names and channel keys

        Args:
         - channel_string: Channel string to parse

        Returns:
         - channel_map: Tuple containing names of channels to load and corresponding keys
        '''

        char_store = ''  # Used for storing the first character for expression with two characters
        channel_selector = ''  # Used for storing the channel name
        channel_names = []  # List of channel names
        channel_keys = []  # List of channel keys

        for char in channel_string:
            # Map characters to channel names
            if char == 'c':
                channel_selector = '.IndexOB.X'
            if char == 'i':
                channel_selector = '.IndexMA.X'
            if char == 'r':
                channel_selector = '.Combined.R'
            if char == 'g':
                channel_selector = '.Combined.G'
            if char == 'b':
                channel_selector = '.Combined.B'
            if char == 'a':
                channel_selector = '.Combined.A'
            if char == 'd':
                channel_selector = '.Depth.Z'
            if char == 'n':
                channel_selector = '.Normal'
            if char == 'f':
                channel_selector = '.Vector'

            # Store character if it is the start of a two character expression
            if char in self.two_char_expr_starts:
                char_store = char
            # Finish two character expression
            elif char_store:
                if char == 'x':
                    channel_selector += '.X'
                if char == 'y':
                    channel_selector += '.Y'
                if char == 'z':
                    channel_selector += '.Z'
                if char == 'w':
                    channel_selector += '.W'
                
                channel_names.append(channel_selector)
                channel_keys.append(char_store+char)
                channel_selector = ''
                char_store = ''
            # Finish expression
            elif channel_selector and not char_store:
                channel_names.append(channel_selector)
                channel_keys.append(char)
                channel_selector = ''
                char_store = ''

        channel_map = ([self.view_layer_name + c for c in channel_names], channel_keys)
        return channel_map


    def _load_channels(self, channel_names: list, channel_keys:list) -> None:
        '''Load given channels in self.channels dictionary

        Args:
         - channel_names: Names of the channels to load
         - channel_keys: Keys under which the channel data values will be stored in self.channels
        '''
        # Only load channels that are not loaded yet
        channel_names = [c for c in channel_names if c not in self.channels]

        if channel_names:
            channels = self.inputfile.channels(channel_names)  # Get channel values as a list of bytes objects
            # Load data and store it in self.channels
            for channel, channel_key in zip(channels, channel_keys):
                if not self.loader:
                    self.channels[channel_key] = array('f', channel).tolist()
                else:
                    self.channels[channel_key] = self.loader.frombuffer(channel, dtype=self.loader.float32)
