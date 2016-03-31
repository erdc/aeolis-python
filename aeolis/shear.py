import scipy.interpolate
import scipy.special


class WindShear:
    '''Class for computation of 2DH wind shear perturbations over a topography.
        
    The class implements a 2D FFT solution to the wind shear
    perturbation on curvilinear grids.  As the FFT solution is only
    defined on an equidistant rectilinear grid with circular boundary
    conditions that is aligned with the wind direction, a rotating
    computational grid is automatically defined for the computation.
    The computational grid is extended in all directions using a
    sigmoid function as to ensure full coverage of the input grid for
    all wind directions and a circular boundaries.  An extra buffer
    distance can be used as to minimize the disturbence from the
    borders in the input grid.  The results are interpolated back to
    the input grid when necessary.

    '''

    
    igrid = {}
    cgrid = {}
    
    
    def __init__(self, x, y, z, dx=1., dy=1., buffer_width=100., buffer_relaxation=None, L=100., z0=.001, l=10.):
        '''Class initialization
            
        Parameters
        ----------
        x : numpy.ndarray
            2D array with x-coordinates of input grid
        y : numpy.ndarray
            2D array with y-coordinates of input grid
        z : numpy.ndarray
            2D array with topography of input grid
        dx : float, optional
            Grid spacing in x dimension of computational grid
            (default: 1)
        dy : float, optional
            Grid spacing of y dimension of computational grid
            (default: 1)
        buffer_width : float, optional
            Width of buffer distance between input grid boundary and
            computational grid boundary (default: 100)
        buffer_relaxation : float, optional
            Relaxation of topography in buffer from input grid
            boundary to computational grid boundary (default:
            buffer_width / 4)
        L : float, optional
            Length scale of topographic features (default: 100)
        z0 : float, optional
            Aerodynamic roughness (default: .001)
        l : float, optional
            Height of inner layer (default: 10)

        '''
        
        if buffer_relaxation is None:
            buffer_relaxation = buffer_width / 4.
        
        self.igrid = dict(x = x,
                          y = y,
                          z = z)
            
        self.cgrid = dict(dx = dx,
                          dy = dy)
                          
        self.buffer_width = buffer_width
        self.buffer_relaxation = buffer_relaxation
                          
        self.L = L
        self.z0 = z0
        self.l = l
                          
        self.set_computational_grid()


    def __call__(self, u0, udir):
        '''Compute wind shear for given wind speed and direction
        
        Parameters
        ----------
        u0 : float
            Free-flow wind speed
        udir : float
            Wind direction in degrees
        
        '''
            
        self.populate_computational_grid(udir)
        self.compute_shear(u0)
                    
        gc = self.cgrid
        gi = self.igrid
                            
        dtaux, dtauy = self.rotate(gc['dtaux'], gc['dtauy'], udir)
                                
        #taux = 1.25 * .001 * u0**2 * (1. + gc['dtaux'])
        #tauy = 1.25 * .001 * u0**2 * (0. + gc['dtauy'])
        #taux, tauy = self.rotate(taux, tauy, udir)
                                
        self.cgrid['dtaux'] = dtaux
        self.cgrid['dtauy'] = dtauy
        #self.cgrid['taux'] = taux
        #self.cgrid['tauy'] = tauy
                                        
        self.igrid['dtaux'] = self.interpolate(gc['x'], gc['y'], dtaux, gi['x'], gi['y'])
        self.igrid['dtauy'] = self.interpolate(gc['x'], gc['y'], dtauy, gi['x'], gi['y'])
        #self.igrid['taux'] = self.interpolate(gc['x'], gc['y'], taux, gi['x'], gi['y'])
        #self.igrid['tauy'] = self.interpolate(gc['x'], gc['y'], tauy, gi['x'], gi['y'])
        
        return self


    def get_shear(self):
        '''Returns wind shear perturbation
        
        Returns
        -------
        dtaux : numpy.ndarray
            Wind shear perturbation in x-direction
        dtauy : numpy.ndarray
            Wind shear perturbation in y-direction
        
        '''
            
        return self.igrid['dtaux'], self.igrid['dtauy']
        
        
    def populate_computational_grid(self, alpha):
        '''Interpolate input topography to computational grid
            
        Rotates computational grid to current wind direction and
        interpolates the input topography to the rotated grid. Any
        grid cells that are not covered by the input grid are filled
        using a sigmoid function.
            
        Parameters
        ----------
        alpha : float
            Rotation angle in degrees

        '''
        
        gc = self.cgrid
        gi = self.igrid
        
        xc, yc = self.rotate(gc['xi'], gc['yi'], alpha, origin=(self.x0, self.y0))
        self.cgrid['z'] = interpolate_grid(gi['x'], gi['y'], gi['z'], xc, yc)
        self.cgrid['x'] = xc
        self.cgrid['y'] = yc
        
        px = self.get_borders(gi['x'])
        py = self.get_borders(gi['y'])
        pz = self.get_borders(gi['z'])
        
        ix = np.isnan(gc['z'])
        argmin = lambda x: np.argmin(x), np.min(x)
        i, d = zip(*[argmin(np.sqrt((px - xn)**2 + (py - yn)**2))
                     for xn, yn in zip(xc[ix], yc[ix])])
            
        i = np.asarray(i)
        d = np.asarray(d)
                     
        self.cgrid['z'][ix] = pz[i] * self.get_sigmoid(d)

        
    def compute_shear(self, u0):
        '''Compute wind shear perturbation for given free-flow wind speed on computational grid
        
        Parameters
        ----------
        u0 : float
            Free-flow wind speed
        
        '''
            
        g = self.cgrid
                
        if u0 == 0.:
            self.cgrid['dtaux'] = np.zeros(g['z'].shape)
            self.cgrid['dtauy'] = np.zeros(g['z'].shape)
            return
                                
        ny, nx = g['z'].shape
        kx, ky = np.meshgrid(np.fft.fftfreq(nx+1, 2 * np.pi / (g['dx']*nx))[1:],
                             np.fft.fftfreq(ny+1, 2 * np.pi / (g['dy']*ny))[1:])
        hs = -np.fft.fft2(g['z']);
                                            
        k = np.sqrt(kx**2 + ky**2)
        sigma = np.sqrt(1j * self.L / 4. * kx * self.z0 / self.l)
        
        dtaux_t = hs * kx**2 / k * 2 / u0**2 * \
                  (-1 + (2 * np.log(self.l/self.z0) + k**2/kx**2) * sigma * \
                   scipy.special.jn(1, 2 * sigma) / scipy.special.jn(0, 2 * sigma))
        dtauy_t = hs * kx * ky / k * 2 / u0**2 * \
                  2 * np.sqrt(2) * sigma * scipy.special.jn(1, 2 * np.sqrt(2) * sigma)
        
        self.cgrid['dtaux'] = np.real(np.fft.ifft2(dtaux_t))
        self.cgrid['dtauy'] = np.real(np.fft.ifft2(dtauy_t))
        
        
    def set_computational_grid(self):
        '''Define computational grid
        
        The computational grid is square with dimensions equal to the
        diagonal of the bounding box of the input grid, plus twice the
        buffer width.

        '''
            
        g = self.igrid
                
        # grid center
        x0, y0 = np.mean(g['x']), np.mean(g['y'])
                    
        # grid size
        self.D = np.sqrt((g['x'].max() - g['x'].min())**2 +
                         (g['y'].max() - g['y'].min())**2) + 2 * self.buffer_width
                        
        # determine equidistant, square grid
        xc, yc = get_exact_grid(x0 - self.D/2., x0 + self.D/2.,
                                y0 - self.D/2., y0 + self.D/2.,
                                self.cgrid['dx'], self.cgrid['dy'])
        
        self.x0 = x0
        self.y0 = y0
        self.cgrid['xi'] = xc
        self.cgrid['yi'] = yc
        
        
    def get_sigmoid(self, x):
        '''Get sigmoid function value
        
        Get bed level multiplication factor in buffer area based on
        buffer specificationa and distance to input grid boundary.
        
        Parameters
        ----------
        x : float or numpy.ndarray
            Distance(s) to input grid boundary
        
        Returns
        -------
        float or numpy.ndarray
            Bed level multiplication factor (z = factor * z_boundary)

        '''
            
        return 1. / (1. + np.exp(-(self.buffer_width-x) / self.buffer_relaxation))
        
        
    def plot(self, ax=None, cmap='Reds', stride=10, computational_grid=False, **kwargs):
        '''Plot wind shear perturbation
            
        Parameters
        ----------
        ax : matplotlib.pyplot.Axes, optional
            Axes to plot onto
        cmap : matplotlib.cm.Colormap or string, optional
            Colormap for topography (default: Reds)
        stride : int, optional
            Stride to apply to wind shear vectors (default: 10)
        computational_grid : bool, optional
            Plot on computational grid rather than input grid
            (default: False)
        **kwargs : dict
            Additional arguments to :func:`matplotlib.pyplot.quiver`
            
        Returns
        -------
        ax : matplotlib.pyplot.Axes
            Axes used for plotting

        '''
        
        d = stride
        
        if ax is None:
            fig, ax = subplots()
        
        if computational_grid:
            g = self.cgrid
        else:
            g = self.igrid
        
        ax.pcolormesh(g['x'], g['y'], g['z'], cmap=cmap)
        ax.quiver(g['x'][::d,::d], g['y'][::d,::d], 
                  g['dtaux'][::d,::d], g['dtauy'][::d,::d], **kwargs)
                  
        if computational_grid:
            ax.plot(self.get_borders(self.igrid['x']),
                    self.get_borders(self.igrid['y']), '-k')
                  
        return ax


    @staticmethod
    def get_exact_grid(xmin, xmax, ymin, ymax, dx, dy):
        '''Returns a grid with given gridsizes approximately within given bounding box'''
        
        x = np.arange(np.floor(xmin / dx) * dx,
                      np.ceil(xmax / dx) * dx, dx)
        y = np.arange(np.floor(ymin / dy) * dy,
                      np.ceil(ymax / dy) * dy, dy)
        x, y = np.meshgrid(x, y)
                      
        return x, y
    
    
    @staticmethod
    def get_borders(x):
        '''Returns borders of a grid as one-dimensional array'''
        
        return np.concatenate((x[0,:].T, 
                               x[1:-1,-1], 
                               x[-1,::-1].T, 
                               x[-1:1:-1,0],
                               x[0,:1]), axis=0)
    
    
    @staticmethod
    def rotate(x, y, alpha, origin=(0,0)):
        '''Rotate a matrix over given angle around given origin'''
        
        xr = x - origin[0]
        yr = y - origin[1]
        
        a = alpha / 180. * np.pi
        
        R = np.asmatrix([[np.cos(a), -np.sin(a)],
                         [np.sin(a),  np.cos(a)]])
        
        xy = np.concatenate((xr.reshape((-1,1)), 
                             yr.reshape((-1,1))), axis=1) * R
                         
        return (np.asarray(xy[:,0].reshape(x.shape) + origin[0]),
                np.asarray(xy[:,1].reshape(y.shape) + origin[1]))
    
    
    @staticmethod
    def interpolate(x, y, z, xi, yi):
        '''Interpolate a grid onto another grid'''
        
        xy = np.concatenate((x.reshape((-1,1)),
                             y.reshape((-1,1))), axis=1)
        xyi = np.concatenate((xi.reshape((-1,1)),
                              yi.reshape((-1,1))), axis=1)
        
        z = scipy.interpolate.griddata(xy, z.reshape((-1,1)), xyi, method='cubic').reshape(xi.shape)
                             
        return z
