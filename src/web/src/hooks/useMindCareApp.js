import { useEffect, useMemo, useRef, useState } from "react";
import { STORAGE_KEYS } from "../config/api";
import { authApi, catalogApi, coursesApi, visitsApi } from "../services/mindcareApi";

const FEEDBACK_DURATION_MS = 3600;

function loadCachedUser() {
  const cached = localStorage.getItem(STORAGE_KEYS.user);
  if (!cached) return null;
  try {
    return JSON.parse(cached);
  } catch {
    return null;
  }
}

function buildOptimisticMessage(text) {
  return {
    id: `local-${Date.now()}`,
    role: "user",
    text,
  };
}

function normalizeCourseList(courses) {
  return (courses || []).map((course) => ({
    ...course,
    school: course.school || null,
  }));
}

export function useMindCareApp() {
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEYS.token) || "");
  const [user, setUser] = useState(loadCachedUser);

  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ username: "", password: "" });
  const [showAuthModal, setShowAuthModal] = useState(false);

  const [showSchoolModal, setShowSchoolModal] = useState(false);
  const [showCompleteCourseModal, setShowCompleteCourseModal] = useState(false);
  const [showCreateCourseModal, setShowCreateCourseModal] = useState(false);

  const [schools, setSchools] = useState([]);
  const [selectedSchoolId, setSelectedSchoolId] = useState("");

  const [courses, setCourses] = useState([]);
  const [currentCourse, setCurrentCourse] = useState(null);
  const [visits, setVisits] = useState([]);
  const [currentVisit, setCurrentVisit] = useState(null);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [selectedVisitId, setSelectedVisitId] = useState("");

  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const chatEndRef = useRef(null);
  const feedbackTimerRef = useRef(null);

  function clearFeedback() {
    if (feedbackTimerRef.current) {
      clearTimeout(feedbackTimerRef.current);
      feedbackTimerRef.current = null;
    }
    setFeedback(null);
  }

  function pushFeedback(type, message, options = {}) {
    const { sticky = false } = options;
    if (!message) return;

    if (feedbackTimerRef.current) {
      clearTimeout(feedbackTimerRef.current);
      feedbackTimerRef.current = null;
    }

    setFeedback({
      type,
      message,
      timestamp: Date.now(),
    });

    if (!sticky) {
      feedbackTimerRef.current = setTimeout(() => {
        setFeedback(null);
        feedbackTimerRef.current = null;
      }, FEEDBACK_DURATION_MS);
    }
  }

  const resetAuthState = () => {
    setToken("");
    setUser(null);
    setCourses([]);
    setCurrentCourse(null);
    setVisits([]);
    setCurrentVisit(null);
    setSelectedCourseId("");
    setSelectedVisitId("");
    setShowCreateCourseModal(false);
    localStorage.removeItem(STORAGE_KEYS.token);
    localStorage.removeItem(STORAGE_KEYS.user);
  };

  useEffect(() => {
    return () => {
      if (feedbackTimerRef.current) {
        clearTimeout(feedbackTimerRef.current);
      }
    };
  }, []);

  const onUnauthorized = () => {
    resetAuthState();
    pushFeedback("info", "Session expired. Please sign in again to continue.", { sticky: true });
  };

  function syncCourseInList(nextCourse) {
    setCourses((prev) => {
      const exists = prev.some((course) => course.course_id === nextCourse.course_id);
      if (!exists) {
        return [nextCourse, ...prev];
      }
      return prev.map((course) =>
        course.course_id === nextCourse.course_id ? { ...course, ...nextCourse } : course
      );
    });
  }

  function syncVisitInList(nextVisit) {
    setVisits((prev) => {
      const exists = prev.some((visit) => visit.visit_id === nextVisit.visit_id);
      if (!exists) {
        return [...prev, nextVisit].sort((a, b) => a.visit_no - b.visit_no);
      }
      return prev.map((visit) => (visit.visit_id === nextVisit.visit_id ? { ...visit, ...nextVisit } : visit));
    });
  }

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [currentVisit?.messages, isTyping]);

  useEffect(() => {
    void loadSchools();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (token) {
      if (!selectedSchoolId && schools.length > 0) {
        setSelectedSchoolId(schools[0].id);
      }
      void loadCourses(selectedSchoolId || (schools[0] && schools[0].id), token);
      return;
    }

    setCourses([]);
    setCurrentCourse(null);
    setVisits([]);
    setCurrentVisit(null);
    setSelectedCourseId("");
    setSelectedVisitId("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedSchoolId]);

  useEffect(() => {
    if (!selectedSchoolId && schools.length > 0) {
      setSelectedSchoolId(schools[0].id);
    }
  }, [schools, selectedSchoolId]);

  async function loadSchools() {
    try {
      const data = await catalogApi.listSchools();
      setSchools(data);
    } catch (error) {
      pushFeedback("error", error.message || "Failed to load counseling modalities.", { sticky: true });
    }
  }

  async function loadCourses(schoolId = selectedSchoolId, tokenOverride = token) {
    if (!tokenOverride) return;

    try {
      const data = await coursesApi.list(
        schoolId ? { school_id: schoolId } : {},
        { token: tokenOverride, onUnauthorized }
      );

      const normalized = normalizeCourseList(data);
      setCourses(normalized);

      const hasCurrentCourse = selectedCourseId && normalized.some((course) => course.course_id === selectedCourseId);

      if (normalized.length === 0) {
        setCurrentCourse(null);
        setVisits([]);
        setCurrentVisit(null);
        setSelectedCourseId("");
        setSelectedVisitId("");
        return;
      }

      const candidateCourse = normalized.find((course) => course.status === "active") || normalized[0];
      const targetCourseId = hasCurrentCourse ? selectedCourseId : candidateCourse.course_id;
      if (targetCourseId) {
        await loadCourse(targetCourseId, tokenOverride);
      }
    } catch (error) {
      pushFeedback("error", error.message || "Failed to load course list.", { sticky: true });
    }
  }

  async function loadCourse(courseId, tokenOverride = token) {
    if (!tokenOverride || !courseId) return;

    try {
      const course = await coursesApi.getById(courseId, { token: tokenOverride, onUnauthorized });
      setCurrentCourse(course);
      setSelectedCourseId(course.course_id);
      syncCourseInList(course);
      await loadCourseVisits(course, tokenOverride);
    } catch (error) {
      pushFeedback("error", error.message || "Failed to load course details.", { sticky: true });
    }
  }

  async function loadCourseVisits(course, tokenOverride = token) {
    if (!course?.course_id) return;

    try {
      const visitList = await visitsApi.list(course.course_id, { token: tokenOverride, onUnauthorized });
      const sortedVisits = [...visitList].sort((a, b) => a.visit_no - b.visit_no);
      setVisits(sortedVisits);

      let targetVisit = null;
      if (selectedVisitId) {
        targetVisit = sortedVisits.find((visit) => visit.visit_id === selectedVisitId);
      }
      if (!targetVisit && course.active_visit_id) {
        targetVisit = sortedVisits.find((visit) => visit.visit_id === course.active_visit_id);
      }
      if (!targetVisit && sortedVisits.length > 0) {
        targetVisit = sortedVisits.find((visit) => visit.status === "open") || sortedVisits[sortedVisits.length - 1];
      }

      if (!targetVisit) {
        setCurrentVisit(null);
        setSelectedVisitId("");
        return;
      }

      setSelectedVisitId(targetVisit.visit_id);
      await loadVisit(targetVisit.visit_id, tokenOverride, true);
    } catch (error) {
      pushFeedback("error", error.message || "Failed to load session list.", { sticky: true });
    }
  }

  async function loadVisit(visitId, tokenOverride = token, includeInList = true) {
    if (!tokenOverride || !visitId) return;

    try {
      const visit = await visitsApi.getById(visitId, { token: tokenOverride, onUnauthorized });
      setCurrentVisit(visit);
      setSelectedVisitId(visit.visit_id);
      if (includeInList) {
        syncVisitInList(visit);
      }
    } catch (error) {
      pushFeedback("error", error.message || "Failed to load session.", { sticky: true });
    }
  }

  async function createCourse(payload = {}) {
    const normalizedPayload =
      payload && typeof payload === "object" && "nativeEvent" in payload ? {} : payload;

    if (!token) {
      pushFeedback("info", "Please sign in first.", { sticky: true });
      return null;
    }

    if (!selectedSchoolId) {
      pushFeedback("info", "Please select a counseling modality.", { sticky: true });
      return null;
    }

    try {
      const data = await coursesApi.create(
        {
          school_id: selectedSchoolId,
          auto_start_first_visit: true,
          title: "",
          ...normalizedPayload,
        },
        {
          token,
          onUnauthorized,
        }
      );

      if (data?.course?.course_id) {
        await loadCourse(data.course.course_id, token);
      } else {
        await loadCourses(selectedSchoolId, token);
      }

      pushFeedback("success", "Course created successfully. The initial session has been generated.");
      return data;
    } catch (error) {
      pushFeedback("error", error.message || "Failed to create course.", { sticky: true });
      return null;
    }
  }

  async function startNextVisit() {
    if (!currentCourse) {
      pushFeedback("info", "Please select a course first.", { sticky: true });
      return null;
    }
    if (currentCourse.status !== "active") {
      pushFeedback("info", "Only active courses can start new sessions.", { sticky: true });
      return null;
    }
    if (currentCourse.active_visit_id) {
      pushFeedback("info", "An active session is already in progress for this course.", { sticky: true });
      return null;
    }

    try {
      const visit = await visitsApi.create(currentCourse.course_id, { opening_note: "" }, { token, onUnauthorized });
      syncCourseInList({
        ...currentCourse,
        active_visit_id: visit.visit_id,
        latest_visit_no: visit.visit_no,
      });
      await loadCourse(currentCourse.course_id, token);
      if (visit?.visit_id) {
        setCurrentVisit(visit);
        setSelectedVisitId(visit.visit_id);
      }
      pushFeedback("success", `Session ${visit.visit_no || (currentCourse.latest_visit_no || 0) + 1} started.`);
      return visit;
    } catch (error) {
      pushFeedback("error", error.message || "Failed to create session.", { sticky: true });
      return null;
    }
  }

  async function continueCurrentVisit() {
    if (!currentCourse?.active_visit_id) {
      pushFeedback("info", "There is no active session in progress.", { sticky: true });
      return;
    }
    await loadVisit(currentCourse.active_visit_id, token, true);
  }

  async function selectCourse(courseId) {
    if (!courseId) return;
    setSelectedVisitId("");
    await loadCourse(courseId, token);
    setSidebarOpen(false);
  }

  async function selectVisit(visitId) {
    if (!visitId) return;
    await loadVisit(visitId, token, true);
    setSidebarOpen(false);
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || !currentVisit) return;

    const optimisticMessage = buildOptimisticMessage(text);
    setInput("");
    setIsTyping(true);
    setCurrentVisit((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        messages: [...(prev.messages || []), optimisticMessage],
      };
    });

    try {
      const data = await visitsApi.sendMessage(
        currentVisit.visit_id,
        { text },
        { token, onUnauthorized }
      );
      setCurrentVisit(data.visit);
      if (data?.course_meta?.course_id) {
        await loadCourse(data.course_meta.course_id, token);
      } else if (currentCourse?.course_id) {
        await loadCourse(currentCourse.course_id, token);
      }
    } catch (error) {
      setCurrentVisit((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          messages: (prev.messages || []).filter((msg) => msg.id !== optimisticMessage.id),
        };
      });
      setInput(text);
      pushFeedback("error", error.message || "Failed to send message.", { sticky: true });
    } finally {
      setIsTyping(false);
    }
  }

  async function closeCurrentVisit(payload = {}) {
    const normalizedPayload =
      payload && typeof payload === "object" && "nativeEvent" in payload ? {} : payload;

    if (!currentVisit) return false;
    if (currentVisit.status !== "open") {
      pushFeedback("info", "The current session has already ended.", { sticky: true });
      return false;
    }

    try {
      await visitsApi.close(currentVisit.visit_id, normalizedPayload, { token, onUnauthorized });
      if (currentCourse?.course_id) {
        await loadCourse(currentCourse.course_id, token);
      }
      pushFeedback("success", "Session concluded. You may now begin the next session.");
      return true;
    } catch (error) {
      pushFeedback("error", error.message || "Failed to end current session.", { sticky: true });
      return false;
    }
  }

  async function completeCurrentCourse() {
    if (!currentCourse) {
      pushFeedback("info", "Please select a course first.", { sticky: true });
      return false;
    }
    if (currentCourse.status !== "active") {
      pushFeedback("info", "Only active courses can be completed.", { sticky: true });
      return false;
    }
    if (currentCourse.active_visit_id) {
      pushFeedback("info", "Please conclude the current session before completing the course.", { sticky: true });
      return false;
    }

    try {
      await coursesApi.complete(currentCourse.course_id, {}, { token, onUnauthorized });
      await loadCourse(currentCourse.course_id, token);
      pushFeedback("success", "Course completed successfully.");
      return true;
    } catch (error) {
      pushFeedback("error", error.message || "Failed to complete course.", { sticky: true });
      return false;
    }
  }

  async function handleAuth(mode) {
    const username = authForm.username.trim();
    const password = authForm.password;

    if (!username || !password) {
      pushFeedback("info", "Please enter your username and password.", { sticky: true });
      return;
    }

    try {
      const payload = { username, password };
      const data = mode === "register" ? await authApi.register(payload) : await authApi.login(payload);

      setToken(data.token);
      setUser(data.user);
      localStorage.setItem(STORAGE_KEYS.token, data.token);
      localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(data.user));

      setAuthMode("login");
      setAuthForm({ username: "", password: "" });
      setShowAuthModal(false);

      await loadCourses(selectedSchoolId || "", data.token);
      pushFeedback("success", mode === "register" ? "Registered successfully and signed in." : "Signed in successfully.");
    } catch (error) {
      pushFeedback("error", error.message || "Authentication failed.", { sticky: true });
    }
  }

  function logout() {
    resetAuthState();
    setShowAuthModal(false);
    pushFeedback("info", "Signed out successfully.");
  }

  const currentSchool = useMemo(() => {
    const matched = schools.find((school) => school.id === selectedSchoolId);
    if (matched) return matched;
    if (currentCourse?.school) return currentCourse.school;
    return schools[0] || null;
  }, [currentCourse, schools, selectedSchoolId]);

  const currentStage = useMemo(() => currentVisit?.stage || currentCourse?.current_stage, [currentVisit, currentCourse]);

  const canStartNextVisit = Boolean(
    currentCourse?.status === "active" && currentCourse?.active_visit_id == null
  );
  const canCloseCurrentVisit = Boolean(currentVisit && currentVisit.status === "open");
  const canContinueVisit = Boolean(currentCourse?.active_visit_id);
  const canCompleteCourse = Boolean(currentCourse?.status === "active" && currentCourse?.active_visit_id == null);
  const canCreateCourse = Boolean(token && selectedSchoolId);

  return {
    token,
    user,
    authMode,
    authForm,
    showAuthModal,
    showSchoolModal,
    showCompleteCourseModal,
    showCreateCourseModal,
    schools,
    selectedSchoolId,
    courses,
    visits,
    currentCourse,
    currentVisit,
    currentSchool,
    currentStage,
    input,
    isTyping,
    sidebarOpen,
    sidebarCollapsed,
    feedback,
    chatEndRef,

    setAuthMode,
    setAuthForm,
    setShowAuthModal,
    setShowSchoolModal,
    setShowCompleteCourseModal,
    setShowCreateCourseModal,
    setSelectedSchoolId,
    setInput,
    setSidebarOpen,
    setSidebarCollapsed,
    clearFeedback,

    createCourse,
    startNextVisit,
    continueCurrentVisit,
    closeCurrentVisit,
    completeCurrentCourse,
    sendMessage,
    selectCourse,
    selectVisit,
    loadCourses,
    handleAuth,
    logout,
    canStartNextVisit,
    canCloseCurrentVisit,
    canContinueVisit,
    canCompleteCourse,
    canCreateCourse,
  };
}
