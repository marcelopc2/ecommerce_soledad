from django.contrib import admin
from .models import Course, Lesson, Membership


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_active')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [LessonInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'expires_at', 'is_active_display')
    search_fields = ('user__email',)
    filter_horizontal = ('courses', 'orders')

    @admin.display(description='Activa', boolean=True)
    def is_active_display(self, obj):
        return obj.is_active
