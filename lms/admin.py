from django.contrib import admin
from .models import Course, Lesson, Membership, CourseProgress, LessonProgress, Diploma, DiplomaAward


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('order', 'title', 'slug', 'is_active')
    list_editable = ('order',)
    list_display_links = ('title',)
    ordering = ('order', 'id')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [LessonInline]


@admin.register(CourseProgress)
class CourseProgressAdmin(admin.ModelAdmin):
    list_display = ('membership', 'course', 'completed_at')
    search_fields = ('membership__user__email', 'course__title')


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'expires_at', 'is_active_display')
    search_fields = ('user__email',)
    filter_horizontal = ('courses', 'orders')

    @admin.display(description='Activa', boolean=True)
    def is_active_display(self, obj):
        return obj.is_active


@admin.register(Diploma)
class DiplomaAdmin(admin.ModelAdmin):
    list_display = ('order', 'title', 'is_active')
    list_editable = ('order',)
    list_display_links = ('title',)
    ordering = ('order', 'id')


admin.site.register(LessonProgress)
admin.site.register(DiplomaAward)
