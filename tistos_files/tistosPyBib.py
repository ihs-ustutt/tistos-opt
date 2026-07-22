from pyDtOO import dtDeveloping
from pyDtOO import dtForceDeveloping
from pyDtOO import dtScalarDeveloping
from pyDtOO import dtClusteredSingletonState as stateCounter
import numpy as np
import os
import time
import logging
#logger = import_logger()

from logging.handlers import WatchedFileHandler
def import_logger(filename = 'tistos.log', level = logging.DEBUG):
    logger = logging.getLogger(__name__)
    logger.setLevel(level)
    if not logger.handlers:
        filehandler = WatchedFileHandler(filename)
        filehandler.setLevel(level) 
        filehandler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s : %(message)s'))
        logger.addHandler(filehandler)
    #logger.info(f"Initialized Logger. Filename: {filename}.")
    return logger
logger = import_logger()

### CLASS FOR POSTPROCSESING TISTOS CASE ###
class tistosRunner:
  import sys
    
  OMEGA = 7.53982
  DHZUL = -2.4
  
  def __init__(self, case, prefix, stateNumber, coeff):
    self.case_ = case
    self.prefix_ = prefix
    self.stateNumber_ = stateNumber
    self.coeff_ = coeff
    self.state_ = str(self.prefix_)+'_'+str(self.stateNumber_)
    
    self.weights_ = {"tl":1/3, "n":1, "vl":1/3}
    self.end_time = 500
    
    
    #
    # Init variables
    #
    
    self.P_ = {"n":0}
    self.dH_ = {"n":0}
    self.eta_ = {"n":0}
    self.Vcav_ = {"n":0}
    
    self.addDataList_ = [self.P_, self.dH_, self.eta_, self.Vcav_] #Define for new case...
    
    self.isOk_ = False
      
  @staticmethod
  def TransformPre(stateLabel, x, cVstr):
    return x, cVstr
  
  @staticmethod
  def DoF():
    return [
      {'label': 'cV_ru_alpha_1_ex_0.0', 'min': -0.155, 'max': 0.025}, 
      {'label': 'cV_ru_alpha_1_ex_0.5', 'min': -0.19, 'max': -0.01}, 
      {'label': 'cV_ru_alpha_1_ex_1.0', 'min': -0.19, 'max': -0.01}, 
      {'label': 'cV_ru_alpha_2_ex_0.0', 'min': -0.08, 'max': 0.1}, 
      {'label': 'cV_ru_alpha_2_ex_0.5', 'min': -0.08, 'max': 0.1}, 
      {'label': 'cV_ru_alpha_2_ex_1.0', 'min': -0.08, 'max': 0.07}, 
      {'label': 'cV_ru_offsetM_ex_0.0', 'min': 1.0, 'max': 1.5},
      {'label': 'cV_ru_offsetM_ex_0.5', 'min': 1.0, 'max': 1.5}, 
      {'label': 'cV_ru_offsetM_ex_1.0', 'min': 1.0, 'max': 1.5}, 
      {'label': 'cV_ru_ratio_0.0', 'min': 0.4, 'max': 0.6}, 
      {'label': 'cV_ru_ratio_0.5', 'min': 0.4, 'max': 0.6}, 
      {'label': 'cV_ru_ratio_1.0', 'min': 0.4, 'max': 0.6}, 
      {'label': 'cV_ru_offsetPhiR_ex_0.0', 'min': -0.15, 'max': 0.15}, 
      {'label': 'cV_ru_offsetPhiR_ex_0.5', 'min': -0.15, 'max': 0.15}, 
      {'label': 'cV_ru_offsetPhiR_ex_1.0', 'min': -0.15, 'max': 0.15}, 
      {'label': 'cV_ru_bladeLength_0.0', 'min': 0.4, 'max': 0.8}, 
      {'label': 'cV_ru_bladeLength_0.5', 'min': 0.6, 'max': 1.0}, 
      {'label': 'cV_ru_bladeLength_1.0', 'min': 0.8, 'max': 1.3}, 
      {'label': 'cV_ru_t_le_a_0', 'min': 0.005, 'max': 0.06}, 
      {'label': 'cV_ru_t_le_a_0.5', 'min': 0.005, 'max': 0.06},
      {'label': 'cV_ru_t_le_a_1', 'min': 0.005, 'max': 0.06}, 
      {'label': 'cV_ru_t_mid_a_0', 'min': 0.005, 'max': 0.06}, 
      {'label': 'cV_ru_t_mid_a_0.5', 'min': 0.005, 'max': 0.06},
      {'label': 'cV_ru_t_mid_a_1', 'min': 0.005, 'max': 0.06}, 
      {'label': 'cV_ru_t_te_a_0', 'min': 0.005, 'max': 0.06}, 
      {'label': 'cV_ru_t_te_a_0.5', 'min': 0.005, 'max': 0.06},
      {'label': 'cV_ru_t_te_a_1', 'min': 0.005, 'max': 0.06}, 
      {'label': 'cV_ru_u_mid_a_0', 'min': 0.4, 'max': 0.6}, 
      {'label': 'cV_ru_u_mid_a_0.5', 'min': 0.4, 'max': 0.6},
      {'label': 'cV_ru_u_mid_a_1', 'min': 0.4, 'max': 0.6}
      ]
  
  def ReadResults(self, history):
    omega = tistosRunner.OMEGA
    try:
          
      for i in (["n"]):
        caseDirOf = self.case_+"_"+i+"_"+self.state_
        time_step_holder = self.end_time
        #
        # read openFoam results
        #
        Q_ru_dev = dtScalarDeveloping( dtDeveloping(
          os.path.join(caseDirOf, 'postProcessing/Q_ru_in/100')
          ).Read() )
        pIn_ru_dev = dtScalarDeveloping( dtDeveloping(
          os.path.join(caseDirOf, 'postProcessing/ptot_ru_in/100')
          ).Read() )
        pOut_ru_dev = dtScalarDeveloping( dtDeveloping(
          os.path.join(caseDirOf, 'postProcessing/ptot_ru_out/100')
          ).Read() )
        Vcav = dtScalarDeveloping( dtDeveloping(
          os.path.join(caseDirOf, 'postProcessing/V_CAV/100')
          ).Read() )
        F_dev = dtForceDeveloping( dtDeveloping(
          os.path.join(caseDirOf, 'postProcessing/forces')
          ).Read({'force.dat' : ':,4:10', 'moment.dat' : ':,4:10', '*.*' : ''}) )    

        average_time = int(time_step_holder/10)
        self.P_[i] = F_dev.MomentMeanLast(average_time)[2] * omega
        self.dH_[i] = (pOut_ru_dev.MeanLast(average_time) - pIn_ru_dev.MeanLast(average_time)) / 9.81
        self.eta_[i] = self.P_[i] / (1000. * 9.81 * self.dH_[i] * Q_ru_dev.MeanLast(average_time) )
        self.Vcav_[i] = Vcav.MeanLast(average_time)
        
        # check for last iteration
        self.lastIt_ = int( pIn_ru_dev.LastTime() )
        if (self.lastIt_ != time_step_holder):
          raise ValueError('Max number of iterations not reached.')
          
        # Throw an error in case of a pump
        if np.abs(self.eta_[i]) > 1:
          raise ValueError('Pump detected.')
      #
      # toggle isOk to True
      self.isOk_ = True
      history['DateOfEvaluation'] = time.ctime()
              
    except Exception as e:
      #logger.warning('Catch exception in PostProcessing: %s', e)
      history['DateOfFailure'] = time.ctime()
      history['ReasonOfFailure'] = str(e)
    return history


  def post_proc(self,timestep):
    caseDirOf = self.case_+"_n_"+self.state_
    omega = tistosRunner.OMEGA
    timestep_orig = timestep #offset because different files...
    if timestep > 100:
        post_proc_folder = 100
        timestep_force = timestep
        timestep = timestep - 100 ##laminare zeit abziehen
    else:
        post_proc_folder = 0
        timestep_force = timestep
    Q_ru_dev = dtScalarDeveloping( dtDeveloping(
      os.path.join(caseDirOf, f'postProcessing/Q_ru_in/{post_proc_folder}')
      ).Read() )
    pIn_ru_dev = dtScalarDeveloping( dtDeveloping(
      os.path.join(caseDirOf, f'postProcessing/ptot_ru_in/{post_proc_folder}')
      ).Read() )
    pOut_ru_dev = dtScalarDeveloping( dtDeveloping(
      os.path.join(caseDirOf, f'postProcessing/ptot_ru_out/{post_proc_folder}')
      ).Read() )
    Vcav_ = dtScalarDeveloping( dtDeveloping(
      os.path.join(caseDirOf, f'postProcessing/V_CAV/{post_proc_folder}')
      ).Read() )
    F_dev = dtForceDeveloping( dtDeveloping(
      os.path.join(caseDirOf, f'postProcessing/forces')
      ).Read({'force.dat' : ':,4:10', 'moment.dat' : ':,4:10', '*.*' : ''}) )
    #res = dtDeveloping(
            #os.path.join(caseDirOf, f'postProcessing/residuals/{post_proc_folder}')).Read()
    path_solverInfo = os.path.join(caseDirOf, f'postProcessing/residuals/{post_proc_folder}/solverInfo.dat')
    res_names = np.genfromtxt(path_solverInfo, names=True, skip_header=1).dtype.names
    res = np.genfromtxt(path_solverInfo)    

    average_time = 10 
    res_dict = {}
    P = F_dev.MomentMean(timestep_force, average_time)[2] * omega
    dH = (pOut_ru_dev.Mean(timestep, average_time) - pIn_ru_dev.Mean(timestep, average_time)) / 9.81
    eta = P / (1000. * 9.81 * dH * Q_ru_dev.Mean(timestep, average_time) )
    Vcav = Vcav_.Mean(timestep, average_time)
    if post_proc_folder == 0:
        #res = res[-1,[3,6,9,14]]
        header_list = ['Ux_final', 'Uy_final', 'Uz_final', 'p_final'] #, 'k_final', 'omega_final']
        indice_list = [3,6,9,14]
        for i, header in enumerate(header_list):
            assert res_names[indice_list[i]] == header, 'Header Error'
            res_dict.update({header: float(res[timestep-1,indice_list[i]])})
            assert res[timestep-1,0] == timestep, f'timestep = {timestep} and time in res = {res[timestep-1,0]}'
        res_dict.update({'k_final': 0.0})    #artificial residuals for k, omega in laminar part
        res_dict.update({'omega_final': 0.0})
    else:
        #res = res[-1,[3,6,9,24,14,19]]         #Ux_final, Uy_final, Uz_final, p_final, k_final, omega_final
        header_list = ['Ux_final', 'Uy_final', 'Uz_final', 'p_final', 'k_final', 'omega_final']
        indice_list = [3,6,9,24,14,19]
        for i, header in enumerate(header_list):
            assert res_names[indice_list[i]] == header, 'Header Error'
            res_dict.update({header: float(res[timestep-1,indice_list[i]])})
            assert res[timestep-1,0] == timestep_orig, f'timestep = {timestep} and time in res = {res[timestep-1,0]}'
    return float(P), float(dH), float(eta), float(Vcav), res_dict


  @staticmethod
  def FailedFitness():
    return [tistosRunner.sys.float_info.max]

  @staticmethod
  def IsFailedFitness(fit):
    if fit[0] == tistosRunner.sys.float_info.max:
      return True
    else:
      return False
      
  def GiveFitness(self):
    dHZul = tistosRunner.DHZUL
    fitnessEta, fitnessVcav, fitnessH = 0.0, 0.0, 0.0
    devH = 1e6
    if self.isOk_:
      ### calculate fitness
      # deviation from design head
      devH = np.abs(self.dH_['n']/dHZul -1)
      # deviation from design head must be <= 20%, otherwise individual
      # is invalid. Multiplication of penalty term with deviation from design
      # head --> If two indivuduals are invalid, the individual with the lower
      # violation of the constraint is dominant.
      #if devH > 0.2:
        #return [1e6*devH]
      for i in ("n"):
        fitnessEta += self.weights_[i] * np.abs(1+self.eta_[i]) 
        fitnessVcav += self.weights_[i] * self.Vcav_[i] 
      fitnessH = np.abs(self.dH_['n'] - dHZul)
      ### single objective fitness ###     
      fitness = np.tanh(fitnessEta) + np.tanh(fitnessVcav * 1e6) + np.tanh(fitnessH)
      fitness_extra = {'dH': self.dH_['n'], 'eta': self.eta_['n'], 
                       'VCav': self.Vcav_['n'], 'P': self.P_['n']}
      ### get residuals and stuff 
    else:
      fitness_extra = {'dH': self.dH_['n'], 'eta': self.eta_['n'],
                       'VCav': self.Vcav_['n'], 'P': self.P_['n']}
      fitness = 3.0
    self.extract_residuals(fitness_extra)
    return fitness, fitness_extra      
    

  def extract_residuals(self,fitness_extra):
      ### get residuals and stuff 
      res = []
      P = []
      dH = []
      eta = []
      Vcav = []
      Ux_final =[]
      Uy_final = []
      Uz_final = []
      p_final = []
      k_final = []
      omega_final = []
      time_list = []
      end_time = self.end_time
      for timestep in np.arange(20,end_time+20,20):
          try:
              P_temp, dH_temp, eta_temp, Vcav_temp, res = self.post_proc(timestep)
              P.append(P_temp)
              dH.append(dH_temp)
              eta.append(eta_temp)
              Vcav.append(Vcav_temp)
              time_list.append(int(timestep))
              Ux_final.append(res['Ux_final'])
              Uy_final.append(res['Uy_final'])
              Uz_final.append(res['Uz_final'])
              p_final.append(res['p_final'])
              k_final.append(res['k_final'])
              omega_final.append(res['omega_final'])
          except IndexError:
              if self.isOk_:
                  logger.exception("Index Error")
              break
          except:
              if self.isOk_:
                  logger.exception("Extract_Residuals Exception")
              break
      fitness_extra.update({'res': {'time': time_list,
                                 'P': P,
                                 'dH': dH,
                                 'eta': eta,
                                 'Vcav': Vcav,
                                 'Ux_final': Ux_final,
                                 'Uy_final': Uy_final,
                                 'Uz_final': Uz_final,
                                 'p_final': p_final,
                                 'k_final': k_final,
                                 'omega_final': omega_final}})
                    

                
