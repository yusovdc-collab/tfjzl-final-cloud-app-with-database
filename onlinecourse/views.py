import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import generic
from django.views.decorators.http import require_POST

from .models import (
    Course,
    Enrollment,
    Question,
    Choice,
    Submission,
)

logger = logging.getLogger(__name__)


# User registration
def registration_request(request):
    context = {}

    if request.method == "GET":
        return render(
            request,
            "onlinecourse/user_registration_bootstrap.html",
            context,
        )

    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("psw", "")
        first_name = request.POST.get("firstname", "")
        last_name = request.POST.get("lastname", "")

        if User.objects.filter(username=username).exists():
            context["message"] = "User already exists."
            return render(
                request,
                "onlinecourse/user_registration_bootstrap.html",
                context,
            )

        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password,
        )

        login(request, user)
        return redirect("onlinecourse:index")

    return HttpResponseBadRequest("Invalid request method.")


# User login
def login_request(request):
    context = {}

    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("psw", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:
            login(request, user)
            return redirect("onlinecourse:index")

        context["message"] = "Invalid username or password."

        return render(
            request,
            "onlinecourse/user_login_bootstrap.html",
            context,
        )

    return render(
        request,
        "onlinecourse/user_login_bootstrap.html",
        context,
    )


# User logout
def logout_request(request):
    logout(request)
    return redirect("onlinecourse:index")


# Check enrollment
def check_if_enrolled(user, course):
    if not user.is_authenticated:
        return False

    return Enrollment.objects.filter(
        user=user,
        course=course,
    ).exists()


# Course list
class CourseListView(generic.ListView):
    template_name = "onlinecourse/course_list_bootstrap.html"
    context_object_name = "course_list"

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by("-total_enrollment")[:10]

        for course in courses:
            course.is_enrolled = check_if_enrolled(user, course)

        return courses


# Course details
class CourseDetailView(generic.DetailView):
    model = Course
    template_name = "onlinecourse/course_detail_bootstrap.html"


# Course enrollment
@login_required(login_url="onlinecourse:login")
def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if not check_if_enrolled(user, course):
        Enrollment.objects.create(
            user=user,
            course=course,
            mode="honor",
        )

        course.total_enrollment += 1
        course.save(update_fields=["total_enrollment"])

    return HttpResponseRedirect(
        reverse(
            "onlinecourse:course_details",
            args=(course.id,),
        )
    )


# Extract selected exam answers
def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith("choice_"):
            try:
                choice_id = int(request.POST[key])
                submitted_answers.append(choice_id)
            except (ValueError, TypeError):
                continue

    return submitted_answers


# Submit exam
@login_required(login_url="onlinecourse:login")
@require_POST
def submit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course,
    )

    selected_choice_ids = extract_answers(request)

    valid_choices = Choice.objects.filter(
        id__in=selected_choice_ids,
        question__course=course,
    )

    submission = Submission.objects.create(
        enrollment=enrollment,
    )

    submission.choices.set(valid_choices)

    return redirect(
        "onlinecourse:show_exam_result",
        course_id=course.id,
        submission_id=submission.id,
    )


# Display exam results
@login_required(login_url="onlinecourse:login")
def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__user=request.user,
        enrollment__course=course,
    )

    selected_choice_ids = set(
        submission.choices.values_list("id", flat=True)
    )

    questions = Question.objects.filter(
        course=course,
    ).prefetch_related("choice_set")

    total_score = 0
    possible_score = 0
    question_results = []

    for question in questions:
        choices = list(question.choice_set.all())

        correct_ids = {
            choice.id
            for choice in choices
            if choice.is_correct
        }

        selected_ids = {
            choice.id
            for choice in choices
            if choice.id in selected_choice_ids
        }

        is_correct = selected_ids == correct_ids

        possible_score += question.grade

        if is_correct:
            total_score += question.grade

        question_results.append({
            "question": question,
            "choices": choices,
            "selected_ids": selected_ids,
            "correct_ids": correct_ids,
            "is_correct": is_correct,
        })

    percentage = (
        round((total_score / possible_score) * 100, 2)
        if possible_score > 0
        else 0
    )

    passed = possible_score > 0 and percentage >= 80

    context = {
        "course": course,
        "submission": submission,
        "question_results": question_results,
        "total_score": total_score,
        "possible_score": possible_score,
        "percentage": percentage,
        "passed": passed,
    }

    return render(
        request,
        "onlinecourse/exam_result_bootstrap.html",
        context,
    )