import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './api/auth'
import Nav from './components/Nav'
import MedicationAlarmManager from './components/MedicationAlarmManager'
import UrduPunjabiSupportLocale from './components/UrduPunjabiSupportLocale'
import ExtraPatientLocale from './components/ExtraPatientLocale'
import PatientLayoutLock from './components/PatientLayoutLock'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import NewConsultation from './pages/NewConsultation'
import ConsultationView from './pages/ConsultationView'
import CrossCheckQueue from './pages/CrossCheckQueue'
import PublicShare from './pages/PublicShare'
import AssistantQueue from './pages/AssistantQueue'
import AssistantReview from './pages/AssistantReview'
import SupportSafety from './pages/SupportSafety'
import LearningCentre from './pages/LearningCentre'
import Reminders from './pages/Reminders'

function Protected({children,roles}){const{user,loading}=useAuth();if(loading)return <div className="page"><div className="loading-card">Loading…</div></div>;if(!user)return <Navigate to="/login"/>;if(roles&&!roles.includes(user.role))return <Navigate to="/"/>;return children}
export default function App(){return <><Nav/><MedicationAlarmManager/><ExtraPatientLocale/><PatientLayoutLock/><UrduPunjabiSupportLocale/><Routes>
 <Route path="/login" element={<Login/>}/><Route path="/register" element={<Register/>}/><Route path="/share/:token" element={<PublicShare/>}/>
 <Route path="/" element={<Protected><Dashboard/></Protected>}/><Route path="/new" element={<Protected roles={['doctor','admin']}><NewConsultation/></Protected>}/><Route path="/consultation/:id" element={<Protected><ConsultationView/></Protected>}/>
 <Route path="/assistant" element={<Protected roles={['assistant']}><AssistantQueue/></Protected>}/><Route path="/assistant/:reviewId" element={<Protected roles={['assistant']}><AssistantReview/></Protected>}/>
 <Route path="/cross-check" element={<Protected roles={['doctor','cross_check_doctor','admin']}><CrossCheckQueue/></Protected>}/><Route path="/reminders" element={<Protected roles={['patient']}><Reminders/></Protected>}/>
 <Route path="/learn" element={<Protected><LearningCentre/></Protected>}/><Route path="/support" element={<Protected><SupportSafety/></Protected>}/><Route path="*" element={<Navigate to="/" replace/>}/>
 </Routes></>}
